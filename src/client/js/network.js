export const network = {
  socket: null,

  connect(url) {
    this.socket = new WebSocket(url);
    return this.socket;
  },
};
