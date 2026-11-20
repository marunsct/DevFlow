// A preview's port forwarder (plan WS.4), run inside the preview's container beside the product:
//   node preview_forwarder.js <public port> <inner port>
// Many products listen on 127.0.0.1 only, which the app on the preview network cannot reach. The product is given
// the inner port; this listens on 0.0.0.0:<public port> and pipes each connection to the product on the loopback
// (127.0.0.1, then ::1). A product that binds 0.0.0.0 is reached the same way. It opens the public port only once the
// product answers on the inner one, so the app's "it answers" still means the product does.
'use strict';
const net = require('net');

const [publicPort, innerPort] = process.argv.slice(2).map(Number);
const LOOPBACK = ['127.0.0.1', '::1'];

function reach(hosts, done) {
  const upstream = net.connect(innerPort, hosts[0]);
  let open = false;
  upstream.once('connect', () => {
    open = true;
    done(null, upstream);
  });
  upstream.on('error', (error) => {
    if (open) return; // the connection's own close handlers end both sides
    upstream.destroy();
    if (hosts.length > 1) reach(hosts.slice(1), done);
    else done(error);
  });
}

const server = net.createServer((client) => {
  client.on('error', () => client.destroy());
  reach(LOOPBACK, (error, upstream) => {
    if (error || client.destroyed) {
      if (upstream) upstream.destroy();
      client.destroy();
      return;
    }
    upstream.on('error', () => client.destroy());
    client.on('close', () => upstream.destroy());
    upstream.on('close', () => client.destroy());
    client.pipe(upstream).pipe(client);
  });
});

server.on('error', (error) => {
  console.error(`preview forwarder: cannot listen on port ${publicPort}: ${error.message}`);
  process.exit(1);
});

(function waitForTheProduct() {
  reach(LOOPBACK, (error, probe) => {
    if (error) {
      setTimeout(waitForTheProduct, 250);
      return;
    }
    probe.destroy();
    server.listen(publicPort, '0.0.0.0');
  });
})();
