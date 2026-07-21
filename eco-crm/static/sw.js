/* ─── ECO MÓDULOS CRM — Service Worker (Web Push) ─────────────────────────── */

const CACHE_VERSION = 'eco-crm-v1';

// Escuchar eventos push del servidor
self.addEventListener('push', function (event) {
  let data = { title: 'Eco Módulos CRM', body: '', url: '/' };

  try {
    if (event.data) {
      const parsed = event.data.json();
      data = { ...data, ...parsed };
    }
  } catch (e) {
    data.body = event.data ? event.data.text() : '';
  }

  const options = {
    body: data.body,
    icon: '/static/img/icon-192.png',
    badge: '/static/img/icon-72.png',
    data: { url: data.url || '/' },
    tag: data.tag || 'eco-crm-notif',
    renotify: true,
    requireInteraction: false,
    vibrate: [150, 50, 150],
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Al hacer click en la notificación → abrir o enfocar la URL
self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      // Si ya hay una pestaña del CRM abierta, enfocala y navega
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.focus();
          client.navigate(targetUrl);
          return;
        }
      }
      // Si no, abrir una nueva
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

// Activación inmediata sin esperar recarga
self.addEventListener('activate', function (event) {
  event.waitUntil(clients.claim());
});
