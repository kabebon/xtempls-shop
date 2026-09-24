/* Подключает Telegram WebApp только внутри клиента Telegram и только с нашего домена.
   В обычном браузере запросов на telegram.org нет, страница не ждёт внешний скрипт. */
(function () {
  var ua = navigator.userAgent || '';
  var inside = /Telegram/i.test(ua)
    || typeof window.TelegramWebviewProxy !== 'undefined'
    || typeof window.TelegramWebviewProxyProto !== 'undefined';
  if (!inside) return;
  document.write('<script src="/telegram-web-app.js" defer><\/script>');
})();
