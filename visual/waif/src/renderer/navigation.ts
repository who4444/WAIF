const CELL_SIZE = 40

export class NavigationMap {
  cols: number
  rows: number
  cellSize: number

  constructor(screenW: number, screenH: number) {
    this.cellSize = CELL_SIZE
    this.cols = Math.ceil(screenW / CELL_SIZE)
    this.rows = Math.ceil(screenH / CELL_SIZE)
  }

  // convert screen coords to grid cell
  toCell(x: number, y: number) {
    return {
      col: Math.floor(x / this.cellSize),
      row: Math.floor(y / this.cellSize),
    }
  }
}