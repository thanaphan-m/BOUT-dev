from __future__ import division

import numpy as np
from boututils import datafile as bdata
from collections import namedtuple
from itertools import chain

from . import fieldtracer
from .progress import update_progress

# PyEVTK might be called pyevtk or evtk, depending on where it was
# installed from
have_evtk = True
try:
    from pyevtk.hl import gridToVTK
except ImportError:
    try:
        from evtk.hl import gridToVTK
    except ImportError:
        have_evtk = False


def parallel_slice_field_name(field, offset):
    """Form a unique, backwards-compatible name for field at a given offset

    Parameters
    ----------
    field : str
        Name of the field to convert
    offset : int
        Parallel slice offset

    """
    prefix = 'forward' if offset > 0 else 'backward'
    suffix = "_{}".format(abs(offset)) if abs(offset) > 1 else ""
    return "{}_{}{}".format(prefix, field, suffix)


def make_maps(grid, magnetic_field, nslice=1, quiet=False, **kwargs):
    """Make the forward and backward FCI maps

    Parameters
    ----------
    grid : :py:obj:`zoidberg.grid.Grid`
        Grid generated by Zoidberg
    magnetic_field : :py:obj:`zoidberg.field.MagneticField`
        Zoidberg magnetic field object
    nslice : int
        Number of parallel slices in each direction
    quiet : bool
        Don't display progress bar
    kwargs
        Optional arguments for field line tracing, etc.

    Returns
    -------
    dict
        Dictionary containing the forward/backward field line maps

    """

    # Get number of points
    # Note: Assumes that all poloidal grids have the same number of x and z(y) points
    ny = grid.numberOfPoloidalGrids()
    pol, _ = grid.getPoloidalGrid(0)
    nx = pol.nx
    nz = pol.nz

    shape = (nx, ny, nz)

    # Coordinates of each grid point
    R = np.zeros(shape)
    Z = np.zeros(shape)

    for j in range(ny):
        pol, _ = grid.getPoloidalGrid(j)
        R[:, j, :] = pol.R
        Z[:, j, :] = pol.Z

    field_tracer = fieldtracer.FieldTracer(magnetic_field)

    rtol = kwargs.get("rtol", None)

    # The field line maps and coordinates, etc.
    maps = {
        'R': R,
        'Z': Z,
    }

    # A helper data structure that groups the various field line maps along with the offset
    ParallelSlice = namedtuple('ParallelSlice', ['offset', 'R', 'Z', 'xt_prime', 'zt_prime'])
    # A list of the above data structures for each offset we want
    parallel_slices = []

    # Loop over offsets {1, ... nslice, -1, ... -nslice}
    for offset in chain(range(1, nslice + 1), range(-1, -(nslice + 1), -1)):
        # Unique names of the field line maps for this offset
        field_names = [parallel_slice_field_name(field, offset)
                       for field in ['R', 'Z', 'xt_prime', 'zt_prime']]

        # Initialise the field arrays -- puts them straight into the result dict
        for field in field_names:
            maps[field] = np.zeros(shape)

        # Get the field arrays we just made and wrap them up in our helper tuple
        fields = map(lambda x: maps[x], field_names)
        parallel_slices.append(ParallelSlice(offset, *fields))

    # Total size of the progress bar
    total_work = float((len(parallel_slices) - 1) * (ny-1))

    # TODO: if axisymmetric, don't loop, do one slice and copy
    # TODO: restart tracing for adjacent offsets
    for slice_index, parallel_slice in enumerate(parallel_slices):
        for j in range(ny):
            if (not quiet) and (ny > 1):
                update_progress(float(slice_index * j) / total_work, **kwargs)

            # Get this poloidal grid
            pol, ycoord = grid.getPoloidalGrid(j)

            # Get the next poloidal grid
            pol_slice, y_slice = grid.getPoloidalGrid(j + parallel_slice.offset)

            # We only want the end point, as [0,...] is the initial position
            coord = field_tracer.follow_field_lines(pol.R, pol.Z, [ycoord, y_slice], rtol=rtol)[1, ...]

            # Store the coordinates in real space
            parallel_slice.R[:, j, :] = coord[:, :, 0]
            parallel_slice.Z[:, j, :] = coord[:, :, 1]

            # Get the indices into the slice poloidal grid
            if pol_slice is None:
                # No slice grid, so hit a boundary
                xind = -1
                zind = -1
            else:
                # Find the indices for these new locations on the slice poloidal grid
                xcoord = coord[:, :, 0]
                zcoord = coord[:, :, 1]
                xind, zind = pol_slice.findIndex(xcoord, zcoord)

                # Check boundary defined by the field
                outside = magnetic_field.boundary.outside(xcoord, y_slice, zcoord)
                xind[outside] = -1
                zind[outside] = -1

            parallel_slice.xt_prime[:, j, :] = xind
            parallel_slice.zt_prime[:, j, :] = zind

    return maps


def write_maps(grid, magnetic_field, maps, gridfile='fci.grid.nc',
               new_names=False, metric2d=True, format="NETCDF3_64BIT",
               quiet=False):
    """Write FCI maps to BOUT++ grid file

    Parameters
    ----------
    grid : :py:obj:`zoidberg.grid.Grid`
        Grid generated by Zoidberg
    magnetic_field : :py:obj:`zoidberg.field.MagneticField`
        Zoidberg magnetic field object
    maps : dict
        Dictionary of FCI maps
    gridfile : str, optional
        Output filename
    new_names : bool, optional
        Write "g_yy" rather than "g_22"
    metric2d : bool, optional
        Output only 2D metrics
    format : str, optional
        Specifies file format to use, passed to boutdata.DataFile
    quiet : bool, optional
        Don't warn about 2D metrics

    Returns
    -------

    Writes the following variables to the grid file


    """

    nx, ny, nz = grid.shape
    # Get metric tensor
    metric = grid.metric()

    # Check if the magnetic field is in cylindrical coordinates
    # If so, we need to change the gyy and g_yy metrics
    pol_grid, ypos = grid.getPoloidalGrid(0)
    Rmaj = magnetic_field.Rfunc(pol_grid.R, pol_grid.Z, ypos)
    if Rmaj is not None:
        # In cylindrical coordinates
        Rmaj = np.zeros(grid.shape)
        for yindex in range(grid.numberOfPoloidalGrids()):
            pol_grid, ypos = grid.getPoloidalGrid(yindex)
            Rmaj[:, yindex, :] = magnetic_field.Rfunc(pol_grid.R, pol_grid.Z, ypos)
        metric["gyy"] = 1./Rmaj**2
        metric["g_yy"] = Rmaj**2

    # Get magnetic field and pressure
    Bmag = np.zeros(grid.shape)
    pressure = np.zeros(grid.shape)
    for yindex in range(grid.numberOfPoloidalGrids()):
        pol_grid, ypos = grid.getPoloidalGrid(yindex)
        Bmag[:, yindex, :] = magnetic_field.Bmag(pol_grid.R, pol_grid.Z, ypos)
        pressure[:, yindex, :] = magnetic_field.pressure(pol_grid.R, pol_grid.Z, ypos)

        metric["g_yy"][:, yindex, :] = (metric["g_yy"][:, yindex, :]
                                        * (Bmag[:, yindex, :]
                                           / magnetic_field.Byfunc(pol_grid.R, pol_grid.Z, ypos))**2)
        metric["gyy"][:, yindex, :] = (metric["gyy"][:, yindex, :]
                                       * (magnetic_field.Byfunc(pol_grid.R, pol_grid.Z, ypos)
                                          / Bmag[:, yindex, :])**2)

    # Get attributes from magnetic field (e.g. psi)
    attributes = {}
    for name in magnetic_field.attributes:
        attribute = np.zeros(grid.shape)
        for yindex in range(grid.numberOfPoloidalGrids()):
            pol_grid, ypos = grid.getPoloidalGrid(yindex)
            attribute[:, yindex, :] = magnetic_field.attributes[name](pol_grid.R, pol_grid.Z, ypos)
            attributes[name] = attribute

    # Metric is now 3D
    if metric2d:
        # Remove the Z dimension from metric components
        if not quiet:
            print("WARNING: Outputting 2D metrics, discarding metric information.")
        for key in metric:
            try:
                metric[key] = metric[key][:, :, 0]
            except TypeError:
                pass
        # Make dz a constant
        metric["dz"] = metric["dz"][0, 0]
        # Add Rxy, Bxy
        metric["Rxy"] = maps["R"][:, :, 0]
        metric["Bxy"] = Bmag[:, :, 0]

    with bdata.DataFile(gridfile, write=True, create=True, format=format) as f:
        ixseps = nx+1
        f.write('nx', nx)
        f.write('ny', ny)
        f.write('nz', nz)

        f.write("dx", metric["dx"])
        f.write("dy", metric["dy"])
        f.write("dz", metric["dz"])

        f.write("ixseps1", ixseps)
        f.write("ixseps2", ixseps)

        # Metric tensor

        if new_names:
            for key, val in metric.items():
                f.write(key, val)
        else:
            # Translate between output variable names and metric names
            # Map from new to old names. Anything not in this dict
            # is output unchanged
            name_changes = {"g_yy": "g_22",
                            "gyy": "g22",
                            "gxx": "g11",
                            "gxz": "g13",
                            "gzz": "g33",
                            "g_xx": "g_11",
                            "g_xz": "g_13",
                            "g_zz": "g_33"}
            for key in metric:
                name = key
                if name in name_changes:
                    name = name_changes[name]
                f.write(name, metric[key])

        # Magnetic field
        f.write("B", Bmag)

        # Pressure
        f.write("pressure", pressure)

        # Attributes
        for name in attributes:
            f.write(name, attributes[name])

        # Maps - write everything to file
        for key in maps:
            f.write(key, maps[key])


def write_Bfield_to_vtk(grid, magnetic_field, scale=5,
                        vtkfile="fci_zoidberg", psi=True):
    """Write the magnetic field to a VTK file

    Parameters
    ----------
    grid : :py:obj:`zoidberg.grid.Grid`
        Grid generated by Zoidberg
    magnetic_field : :py:obj:`zoidberg.field.MagneticField`
        Zoidberg magnetic field object
    scale : int, optional
        Factor to scale x, z dimensions by [5]
    vtkfile : str, optional
        Output filename without extension ["fci_zoidberg"]
    psi : bool, optional
        Write psi?

    Returns
    -------
    path           - Full path to vtkfile
    """

    point_data = {'B' : (magnetic_field.bx*scale,
                         magnetic_field.by,
                         magnetic_field.bz*scale)}

    if psi:
        psi = make_surfaces(grid, magnetic_field)
        point_data['psi'] = psi

    path = gridToVTK(vtkfile,
                     grid.xarray*scale,
                     grid.yarray,
                     grid.zarray*scale,
                     pointData=point_data)

    return path


def fci_to_vtk(infile, outfile, scale=5):

    if not have_evtk:
        return

    with bdata.DataFile(infile, write=False, create=False) as f:
        dx = f.read('dx')
        dy = f.read('dy')

        bx = f.read('bx')
        by = np.ones(bx.shape)
        bz = f.read('bz')
        if bx is None:
            xt_prime = f.read('forward_xt_prime')
            zt_prime = f.read('forward_zt_prime')
            array_indices = indices(xt_prime.shape)
            bx = xt_prime - array_indices[0,...]
            by = by * dy
            bz = zt_prime - array_indices[2,...]

        nx, ny, nz = bx.shape
        dz = nx*dx / nz

    x = np.linspace(0, nx*dx, nx)
    y = np.linspace(0, ny*dy, ny, endpoint=False)
    z = np.linspace(0, nz*dz, nz, endpoint=False)

    gridToVTK(outfile, x*scale, y, z*scale, pointData={'B' : (bx*scale, by, bz*scale)})


def make_surfaces(grid, magnetic_field, nsurfaces=10, revs=100):
    """Essentially interpolate a poincare plot onto the grid mesh

    Parameters
    ----------
    grid : :py:obj:`zoidberg.grid.Grid`
        Grid generated by Zoidberg
    magnetic_field : :py:obj:`zoidberg.field.MagneticField`
        Zoidberg magnetic field object
    nsurfaces : int, optional
        Number of surfaces to interpolate to [10]
    revs : int, optional
        Number of points on each surface [100]

    Returns
    -------
    surfaces
        Array of psuedo-psi on the grid mesh

    """

    from scipy.interpolate import griddata

    # initial x, z points in surface
    xpos = grid.xcentre + np.linspace(0, 0.5*np.max(grid.xarray),
                                           nsurfaces)
    zpos = grid.zcentre

    phi_values = grid.yarray[:]
    # Extend the domain from [0,grid.Ly] to [0,revs*grid.Ly]
    for n in np.arange(1, revs):
        phi_values = np.append(phi_values, n*grid.Ly + phi_values[:grid.ny])

    # Get field line tracer and trace out surfaces
    tracer = fieldtracer.FieldTracer(magnetic_field)
    points = tracer.follow_field_lines(xpos, zpos, phi_values)

    # Reshape to be easier to work with
    points = points.reshape((revs, grid.ny, nsurfaces, 2))

    # Arbitarily number the surfaces from 0 to 1
    psi_points = np.zeros((revs, grid.ny, nsurfaces))
    for surf in range(nsurfaces):
        psi_points[:,:,surf] = float(surf)/float(nsurfaces-1)

    x_2d, z_2d = np.meshgrid(grid.xarray, grid.zarray, indexing='ij')

    psi = np.zeros_like(grid.x_3d)
    for y_slice in range(grid.ny):
        points_2d = np.column_stack((points[:,y_slice,:,0].flatten(),
                                     points[:,y_slice,:,1].flatten()))
        psi[:,y_slice,:] = griddata(points_2d, psi_points[:,y_slice,:].flatten(),
                                    (x_2d, z_2d), method='linear', fill_value=1)

    return psi


def upscale(field, maps, upscale_factor=4, quiet=True):
    """Increase the resolution in y of field along the FCI maps.

    First, interpolate onto the (forward) field line end points, as in
    normal FCI technique. Then interpolate between start and end
    points. We also need to interpolate the xt_primes and
    zt_primes. This gives a cloud of points along the field lines,
    which we can finally interpolate back onto a regular grid.

    Parameters
    ----------
    field : array_like
        3D field to be upscaled
    maps : dict
        Zoidberg field line maps
    upscale_factor : int, optional
        Factor to increase resolution by [4]
    quiet : bool, optional
        Don't show progress bar [True]

    Returns
    -------
    Field with y-resolution increased *upscale_factor* times. Shape is
    (nx, upscale_factor*ny, nz).

    """

    from scipy.ndimage.interpolation import map_coordinates
    from scipy.interpolate import griddata

    xt_prime = maps["forward_xt_prime"]
    zt_prime = maps["forward_zt_prime"]

    # The field should be the same shape as the grid
    if field.shape != xt_prime.shape:
        try:
            field = field.reshape(xt_prime.T.shape).T
        except ValueError:
            raise ValueError("Field, {}, must be same shape as grid, {}"
                             .format(field.shape, xt_prime.shape))

    # Get the shape of the grid
    nx, ny, nz = xt_prime.shape
    index_coords = np.mgrid[0:nx, 0:ny, 0:nz]

    # We use the forward maps, so get the y-index of the *next* y-slice
    yup_3d = index_coords[1,...] + 1
    yup_3d[:,-1,:] = 0

    # Index space coordinates of the field line end points
    end_points = np.array([xt_prime, yup_3d, zt_prime])

    # Interpolation of the field at the end points
    field_prime = map_coordinates(field, end_points)

    # This is a 4D array where the first dimension is the start/end of
    # the field line
    field_aligned = np.array([field, field_prime])

    # x, z coords at start/end of field line
    x_start_end = np.array([index_coords[0,...], xt_prime])
    z_start_end = np.array([index_coords[2,...], zt_prime])

    # Parametric points along the field line
    midpoints = np.linspace(0, 1, upscale_factor, endpoint=False)
    # Need to make this 4D as well
    new_points = np.tile(midpoints[:,np.newaxis,np.newaxis,np.newaxis], [nx, ny, nz])

    # Index space coordinates of our upscaled field
    index_4d = np.mgrid[0:upscale_factor,0:nx,0:ny,0:nz]
    hires_points = np.array([new_points, index_4d[1,...], index_4d[2,...], index_4d[3,...]])

    # Upscale the field
    hires_field = map_coordinates(field_aligned, hires_points)

    # Linearly interpolate the x, z coordinates of the field lines
    hires_x = map_coordinates(x_start_end, hires_points)
    hires_z = map_coordinates(z_start_end, hires_points)

    def twizzle(array):
        """Transpose and reshape the output of map_coordinates to
        be 3D
        """
        return array.transpose((1, 2, 0, 3)).reshape((nx, upscale_factor*ny, nz))

    # Rearrange arrays to be 3D
    hires_field = twizzle(hires_field)
    hires_x = twizzle(hires_x)
    hires_z = twizzle(hires_z)

    # Interpolate from field line sections onto grid
    hires_grid_field = np.zeros( (nx, upscale_factor*ny, nz) )
    hires_index_coords = np.mgrid[0:nx, 0:ny:1./upscale_factor, 0:nz]
    grid_points = (hires_index_coords[0,:,0,:], hires_index_coords[2,:,0,:])

    def y_first(array):
        """Put the middle index first
        """
        return array.transpose((0, 2, 1))

    # The hires data is unstructed only in (x,z), interpolate onto
    # (x,z) grid for each y-slice individually
    for k, (x_points, z_points, f_slice) in enumerate(zip(y_first(hires_x).T, y_first(hires_z).T, y_first(hires_field).T)):
        points = np.column_stack((x_points.flat, z_points.flat))
        hires_grid_field[:,k,:] = griddata(points, f_slice.flat, grid_points,
                                           method='linear', fill_value=0.0)
        if not quiet:
            update_progress(float(k)/float(ny-1))

    return hires_grid_field
