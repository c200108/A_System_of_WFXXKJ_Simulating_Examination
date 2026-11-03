/*!
 * wfxx-collect.js —— 把教学网页里的数据送到教学平台「API」板块
 *
 *   <script src="https://你的服务器/api/hook/sdk.js"></script>
 *   <script>
 *     const api = WFXX.api('接收编号', '写入密钥');      // 地址里 /api/hook/ 后面那串就是编号
 *     api.send({ type: 'answer', student: { no: '20250101', name: '张三' }, score: 8 })
 *        .then(r => console.log(r));                       // { ok: true, id: 123, ... }
 *   </script>
 *
 * 它替你做了这些事：
 * - 自动带 client_id（重发不会重复入库）、来源网页、设备号；
 * - 断网或服务器暂时不可用时先存在浏览器里，联网后／下次打开页面自动补发；
 * - api.beacon(data) 用 sendBeacon 发，关页面的那一刻也能发出去；
 * - api.summary() 取全班汇总（老师在设置里打开「网页可读汇总」才有）。
 */
(function (global) {
  'use strict';
  var script = document.currentScript;
  var BASE = script && script.src ? script.src.replace(/\/api\/hook\/sdk\.js.*$/, '') : '';
  var QKEY = 'wfxx-collect-queue';
  var DKEY = 'wfxx-device-id';

  function uuid() {
    if (global.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 3) | 8).toString(16);
    });
  }
  function store(k, v) {
    try {
      if (v === undefined) return JSON.parse(localStorage.getItem(k) || 'null');
      localStorage.setItem(k, JSON.stringify(v));
    } catch (e) { return null; }
  }
  function device() {
    var d = store(DKEY);
    if (!d) { d = uuid().replace(/-/g, ''); store(DKEY, d); }
    return d;
  }
  function prep(data) {
    var o = {};
    for (var k in data) if (Object.prototype.hasOwnProperty.call(data, k)) o[k] = data[k];
    if (!o.client_id) o.client_id = uuid();
    if (!o.page) o.page = location.href;
    if (!o.submitted_at) o.submitted_at = new Date().toISOString();
    return o;
  }

  function Api(key, token, opts) {
    this.key = key;
    this.token = token;
    this.base = ((opts && opts.base) || BASE).replace(/\/$/, '');
    this.url = this.base + '/api/hook/' + encodeURIComponent(key);
    var self = this;
    global.addEventListener && global.addEventListener('online', function () { self.flush(); });
    setTimeout(function () { self.flush(); }, 1500);
  }

  Api.prototype._post = function (body) {
    return fetch(this.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Api-Key': this.token, 'X-Device-Id': device() },
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.json().catch(function () { return { ok: false, code: 'HTTP_' + res.status }; })
        .then(function (j) { j.status = res.status; return j; });
    });
  };

  /** 发一条（或一个数组批量）。返回 Promise，结果见接入规范 */
  Api.prototype.send = function (data) {
    var self = this;
    var body = Array.isArray(data) ? data.map(prep) : prep(data);
    return this._post(body).then(function (r) {
      if (r.status >= 500 || r.status === 429) self._queue(body);
      return r;
    }, function (err) {
      self._queue(body);
      return { ok: false, code: 'OFFLINE', message: '网络不通，已暂存，联网后自动补发', queued: true };
    });
  };

  /** 关页面时用：sendBeacon 不能带请求头，密钥放在 _token 里 */
  Api.prototype.beacon = function (data) {
    var body = prep(data);
    body._token = this.token;
    var ok = navigator.sendBeacon &&
      navigator.sendBeacon(this.url, new Blob([JSON.stringify(body)], { type: 'text/plain' }));
    if (!ok) this._queue(body);
    return !!ok;
  };

  Api.prototype._queue = function (body) {
    var q = store(QKEY) || [];
    var list = Array.isArray(body) ? body : [body];
    for (var i = 0; i < list.length; i++) q.push({ url: this.url, token: this.token, body: list[i] });
    store(QKEY, q.slice(-500));
  };

  /** 补发暂存的数据 */
  Api.prototype.flush = function () {
    var q = store(QKEY) || [];
    var mine = q.filter(function (x) { return x.url === this.url; }, this);
    if (!mine.length) return Promise.resolve(0);
    var rest = q.filter(function (x) { return x.url !== this.url; }, this);
    var self = this;
    return this._post(mine.map(function (x) { return x.body; })).then(function (r) {
      if (!(r.status >= 500 || r.status === 429)) { store(QKEY, rest); return mine.length; }
      return 0;
    }, function () { return 0; });
  };

  /** 取不含个人信息的汇总（人数、平均分、各题正确率） */
  Api.prototype.summary = function (activity) {
    var u = this.url + '/summary' + (activity ? '?activity=' + encodeURIComponent(activity) : '');
    return fetch(u, { headers: { 'X-Api-Key': this.token } }).then(function (r) { return r.json(); });
  };

  global.WFXX = { api: function (key, token, opts) { return new Api(key, token, opts); }, version: '1.0.0' };
})(window);
