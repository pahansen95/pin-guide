import logging, sys, os, itertools

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr, level=os.environ.get('LOG_LEVEL', 'INFO'))

from build123d import *
from typing import NamedTuple

class Point(NamedTuple):
  x: float
  y: float
  z: float

class GridSize(NamedTuple):
  w: float
  h: float

class GridDims(NamedTuple):
  cols: int
  rows: int

class GridFlag(NamedTuple):
  cols: bool
  rows: bool

UNIT = Unit.IN
GRID_SIZE = GridSize(
  w=9 + 3/4,
  h=7 + 3/4,
)
GRID_DIMS = GridDims(
  cols=5,
  rows=5,
)

"""TODO

Need to Create 2 sets of Grid Lines & Overlay them:

- Odd Number Rows should have columns offset to the left
- Even Number Rows should have columns offset to the right

"""

class GridLines(BaseLineObject):
  def __init__(self,
    grid_size: GridSize,
    grid_dims: GridDims,
    grid_flags: GridFlag = GridFlag(True, True),
    offset: Point = Point(0, 0, 0),
    workplane: Face | Plane | Location = Plane.XY,
    mode: Mode = Mode.ADD,
    **kwargs,
  ):
    """Draw Gridlines on the given Workplane as Edges.

    The inner edges are drawn only.

    Specify the dimensions (ie. rows & cols) & size (ie. WxH) of the grid.

    An Optional offset may be specified which will be applied to all lines. 
    
    """
    assert any(grid_flags)
    ### Determine the min/max X & Y Coords; the grid's center is the origin (0,0)
    x_r = grid_size.w / 2; x_l = -1 * x_r
    y_t = grid_size.h / 2; y_b = -1 * y_t
    verts: dict[str, Point] = {
      'TL': Point(x_l, y_t, 0), 'TR':  Point(x_r, y_t, 0),
      'BL':  Point(x_l, y_b, 0), 'BR':  Point(x_r, y_b, 0),
    }
    col_w = grid_size.w / grid_dims.cols # Divide the total width by the number of columns
    row_w = grid_size.h / grid_dims.rows # Divide the total height by the number of columns

    with BuildLine(workplane=workplane, mode=mode) as lines:
      ### First we create the Column Lines
      if grid_flags.cols:
        for col_no in range(1, grid_dims.cols): # We want to draw lines (1, N-1)
          col_offset = offset.x + verts['TL'].x + col_w * col_no # The right most line of the Column
          Line(
            (col_offset, verts['TL'].y),
            (col_offset, verts['BL'].y),
          )

      ### Then we create the Row Lines
      if grid_flags.rows:
        for row_no in range(1, grid_dims.rows): # We want to draw lines (1, N-1)
          row_offset = offset.y + verts['BL'].y + row_w * row_no # The bottom most line of the Row
          logger.info(f'{row_no=}, {row_offset=}')
          Line(
            (verts['TL'].x, row_offset),
            (verts['TR'].x, row_offset),
          )

    logger.info(f"{lines.line=}")
    super().__init__(curve=lines.line, **kwargs)
    assert len(super().edges()) >1, (grid_dims, super().edges())

logger.info("Building Model")

col_w = GRID_SIZE.w / GRID_DIMS.cols # Divide the total width by the number of columns
row_w = GRID_SIZE.h / GRID_DIMS.rows # Divide the total height by the number of columns

with BuildSketch(Plane.XY) as grid_bg:
  # logger.info(f'{guide.edges()=}')
  Rectangle(
    width=GRID_SIZE.w,
    height=GRID_SIZE.h,
  )
  workplane = grid_bg.face(select=Select.LAST)
with BuildLine(workplane=workplane) as center_lines:
  ### The Center Lines
  GridLines(
    grid_size=GRID_SIZE,
    grid_dims=GRID_DIMS,
    offset=Point(0, 0, 0),
    workplane=workplane,
  )
with BuildLine(workplane=workplane) as left_offset:
  GridLines(
    grid_size=GRID_SIZE,
    grid_dims=GRID_DIMS,
    grid_flags=GridFlag(True, False),
    offset=Point(-(col_w / 4), 0, 0),
    workplane=workplane,
  )
with BuildLine(workplane=workplane) as right_offset:
  GridLines(
    grid_size=GRID_SIZE,
    grid_dims=GRID_DIMS,
    grid_flags=GridFlag(True, False),
    offset=Point(col_w / 4, 0, 0),
    workplane=workplane,
  )

grid_shapes: dict[str, ShapeList] = {
  'bg': ShapeList([
    *grid_bg.faces(),
    *grid_bg.edges()
  ]),
  'center-lines': ShapeList([
    *center_lines.edges(),
  ]),
  'left-offset': ShapeList([
    *left_offset.edges(),
  ]),
  'right-offset': ShapeList([
    *right_offset.edges()
  ])
}
grid_shapes['all'] = ShapeList(itertools.chain.from_iterable(grid_shapes.values()))

svg_export = ExportSVG(
  unit=UNIT,
)
svg_export.add_layer('bg', fill_color=Color(1.0, 1.0, 1.0))
svg_export.add_shape(grid_shapes['bg'], layer='bg')
svg_export.add_layer('center-lines', line_type=LineType.CENTER, line_weight=0.15)
svg_export.add_shape(grid_shapes['center-lines'], layer='center-lines')
svg_export.add_layer('left-offset', line_type=LineType.DASHED, line_weight=0.3)
svg_export.add_shape(grid_shapes['left-offset'], layer='left-offset')
svg_export.add_layer('right-offset', line_type=LineType.DOT2, line_weight=0.3)
svg_export.add_shape(grid_shapes['right-offset'], layer='right-offset')
svg_export.write('.cache/test.svg')

exit(0)
# raise NotImplementedError()

logger.info("Showing Model")
if 'YACV_GRACEFUL_SECS_CONNECT' not in os.environ: os.environ['YACV_GRACEFUL_SECS_CONNECT'] = '0'
if 'YACV_GRACEFUL_SECS_WORK' not in os.environ: os.environ['YACV_GRACEFUL_SECS_WORK'] = '0'
if 'YACV_DISABLE_SERVER' not in os.environ: os.environ['YACV_DISABLE_SERVER'] = '1'
import threading, signal, time
from yacv_server import yacv
(quit_webserver := threading.Event()).clear()
for sig in (
  signal.SIGINT, signal.SIGTERM, signal.SIGQUIT,
): signal.signal(sig, lambda *args, **kwargs: quit_webserver.set())
def webserver(*objs):
  ### NOTE: We do the equivalent of `yacv.start` w/out the stupid signal handling
  assert yacv.server_thread is None, "Server currently running, cannot start another one"
  assert yacv.startup_complete.is_set() is False, "Server already started"
  # Start the server in a separate daemon thread
  yacv.server_thread = threading.Thread(target=yacv._run_server, name='yacv_server', daemon=True)
  yacv.server_thread.start()
  yacv.startup_complete.wait()
  ###
  yacv.show(*objs)
  quit_webserver.wait()
  yacv.stop() 

(t := threading.Thread(
  target=webserver,
  args=(*all_shapes,)
  # args=(guide, *grid_lines,)
)).start()
logger.info('Waiting for Thread to Exit')
t.join()
