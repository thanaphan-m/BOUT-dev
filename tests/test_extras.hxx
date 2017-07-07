#ifndef TEST_EXTRAS_H__
#define TEST_EXTRAS_H__

#include "gtest/gtest.h"

#include <mpi.h>

#include "bout/mesh.hxx"
#include "field3d.hxx"
#include "unused.hxx"

::testing::AssertionResult IsSubString(const std::string &str,
                                       const std::string &substring);

/// FakeMesh has just enough information to create fields
class FakeMesh : public Mesh {
public:
  FakeMesh(int nx, int ny, int nz) {
    GlobalNx = nx;
    GlobalNy = ny;
    GlobalNz = nz;
    LocalNx = nx;
    LocalNy = ny;
    LocalNz = nz;
    xstart = 0;
    xend = nx;
    ystart = 0;
    yend = ny;
  }

  comm_handle send(FieldGroup &UNUSED(g)) { return nullptr; };
  int wait(comm_handle UNUSED(handle)) { return 0; }
  MPI_Request sendToProc(int UNUSED(xproc), int UNUSED(yproc), BoutReal *UNUSED(buffer),
                         int UNUSED(size), int UNUSED(tag)) {
    return MPI_Request();
  }
  comm_handle receiveFromProc(int UNUSED(xproc), int UNUSED(yproc),
                              BoutReal *UNUSED(buffer), int UNUSED(size),
                              int UNUSED(tag)) {
    return nullptr;
  }
  int getNXPE() { return 1; }
  int getNYPE() { return 1; }
  int getXProcIndex() { return 1; }
  int getYProcIndex() { return 1; }
  bool firstX() { return true; }
  bool lastX() { return true; }
  int sendXOut(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return 0; }
  int sendXIn(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return 0; }
  comm_handle irecvXOut(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return nullptr; }
  comm_handle irecvXIn(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return nullptr; }
  MPI_Comm getXcomm(int UNUSED(jy)) const { return MPI_COMM_NULL; }
  MPI_Comm getYcomm(int UNUSED(jx)) const { return MPI_COMM_NULL; }
  bool periodicY(int UNUSED(jx), BoutReal &UNUSED(ts)) const { return true; }
  bool firstY() const { return true; }
  bool lastY() const { return true; }
  bool firstY(int UNUSED(xpos)) const { return true; }
  bool lastY(int UNUSED(xpos)) const { return true; }
  int UpXSplitIndex() { return 0; }
  int DownXSplitIndex() { return 0; }
  int sendYOutIndest(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return 0; }
  int sendYOutOutdest(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return 0; }
  int sendYInIndest(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return 0; }
  int sendYInOutdest(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return 0; }
  comm_handle irecvYOutIndest(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return nullptr; }
  comm_handle irecvYOutOutdest(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return nullptr; }
  comm_handle irecvYInIndest(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return nullptr; }
  comm_handle irecvYInOutdest(BoutReal *UNUSED(buffer), int UNUSED(size), int UNUSED(tag)) { return nullptr; }
  const RangeIterator iterateBndryLowerY() const { return RangeIterator(); }
  const RangeIterator iterateBndryUpperY() const { return RangeIterator(); }
  const RangeIterator iterateBndryLowerOuterY() const { return RangeIterator(); }
  const RangeIterator iterateBndryLowerInnerY() const { return RangeIterator(); }
  const RangeIterator iterateBndryUpperOuterY() const { return RangeIterator(); }
  const RangeIterator iterateBndryUpperInnerY() const { return RangeIterator(); }
  vector<BoundaryRegion*> getBoundaries() { return vector<BoundaryRegion*>(); }
  vector<BoundaryRegionPar*> getBoundariesPar() { return vector<BoundaryRegionPar*>(); }
  BoutReal GlobalX(int UNUSED(jx)) const { return 0; }
  BoutReal GlobalY(int UNUSED(jy)) const { return 0; }
  BoutReal GlobalX(BoutReal UNUSED(jx)) const { return 0; }
  BoutReal GlobalY(BoutReal UNUSED(jy)) const { return 0; }
  int XGLOBAL(int UNUSED(xloc)) const { return 0; }
  int YGLOBAL(int UNUSED(yloc)) const { return 0; }
  const Field3D Switch_YZ(const Field3D &UNUSED(var)) { return Field3D(0.0); }
  const Field3D Switch_XZ(const Field3D &UNUSED(var)) { return Field3D(0.0); }
  void slice_r_y(const BoutReal *, BoutReal *, int , int) {}
  void get_ri(dcomplex *UNUSED(ayn), int UNUSED(n), BoutReal *UNUSED(r), BoutReal *UNUSED(i)) {}
  void set_ri(dcomplex *UNUSED(ayn), int UNUSED(n), BoutReal *UNUSED(r), BoutReal *UNUSED(i)) {}
  const Field2D lowPass_poloidal(const Field2D &,int) { return Field2D(0.0); }
};

#endif //  TEST_EXTRAS_H__
