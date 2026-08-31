export const gameState = {
  player: {
    slot: null,
    hp: 100,
    x: 0,
    y: 0,
    z: 0,
    yaw: 0,
    pitch: 0,
  },
  players: {},
  world: null,
  debug: {
    connected: false,
  },
};

export function setPlayerState(partial) {
  Object.assign(gameState.player, partial);
}
