(async () => {
    const audioElement = document.getElementById('player');
    const MAX_DELAY = 8000;

    let ws;
    let retry = 0;

    function connect() {
        ws = new WebSocket(`wss://${location.host}/ws`);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            console.log('WebSocket open');
            retry = 0;
        };

        let chunks = [];
        ws.onmessage = (event) => {
            if (typeof event.data === 'string') {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'start') {
                        chunks = [];
                    } else if (msg.type === 'end') {
                        const blob = new Blob(chunks, { type: 'audio/mpeg' });
                        const url = URL.createObjectURL(blob);
                        audioElement.src = url;
                        audioElement.play().catch(console.error);
                    }
                } catch (e) {
                    console.error('Bad control message', e);
                }
            } else {
                chunks.push(new Uint8Array(event.data));
            }
        };

        ws.onerror = e => console.error('WebSocket error: ', e);

        ws.onclose = () => {
            console.log('WebSocket closed - attempting to reconnect...');
            scheduleReconnect();
        };

    }

    function scheduleReconnect() {
        const delay = Math.min(500 * (2 ** retry++), MAX_DELAY); // 0.5s, 1s, 2s etc
        setTimeout(connect, delay);
    }

    connect();

})();
