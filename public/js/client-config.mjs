// The launcher replaces this at runtime for public Cloudflare sessions.
export const WSS_URL = 'ws://127.0.0.1:8765';

// Add a TURN server here for players whose networks block direct connections.
export const RTC_ICE_SERVERS = [
	{ urls: 'stun:stun.l.google.com:19302' },
];
