/** 游戏玩家信息 */
export interface PlayerStatus {
  level: number
  gem: number
  stamina: number
}

/** 游戏状态 */
export interface GameStatus {
  current_location: string
  player: PlayerStatus
}

/** 应用整体状态 */
export interface AppStatus {
  platform: string
  yolo: boolean
  task: boolean
  game: GameStatus
}
