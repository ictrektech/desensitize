const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')
const source = ts.transpileModule(fs.readFileSync('src/locale.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText

function fixture({ embedded = true, stored = {}, language = 'en-US' } = {}) {
  const events = new Map()
  let timer
  const window = {
    addEventListener: (name, fn) => events.set(name, fn),
    removeEventListener: (name) => events.delete(name),
    setInterval: fn => { timer = fn; return 1 }, clearInterval: () => { timer = null },
  }
  window.parent = embedded ? {} : window
  const storage = { ...stored }
  Object.defineProperty(storage, 'getItem', { value: key => stored[key] ?? null })
  const context = { exports: {}, window, localStorage: storage, navigator: { languages: [language], language } }
  vm.runInNewContext(source, context)
  return { api: context.exports, window, events, tick: () => timer?.() }
}
const flush = async () => { await new Promise(resolve => setImmediate(resolve)) }

function bridge(snapshot) {
  const listeners = new Set()
  return {
    getState: snapshot,
    broadcast: { on: (_, fn) => { listeners.add(fn); return () => listeners.delete(fn) } },
    emit: locale => listeners.forEach(fn => fn({ locale })),
    listeners,
  }
}

test('embedded fallback recognizes legacy storage key families and locale encodings', () => {
  for (const key of ['preferences-locale', 'VIVIBIT-3.0-preferences-locale', 'vben-web-antd-5-preferences-locale']) {
    for (const value of ['zh-CN', '"zh-CN"', '{"value":"zh-TW"}']) {
      assert.equal(fixture({ stored: { [key]: value } }).api.initialLocale(), 'zh-CN')
    }
  }
})

test('standalone follows browser and ignores unrelated VOS storage', () => {
  assert.equal(fixture({ embedded: false, stored: { 'preferences-locale': 'zh-CN' } }).api.initialLocale(), 'en')
  assert.equal(fixture({ embedded: false, language: 'zh-HK' }).api.initialLocale(), 'zh-CN')
})

test('late bridge injection updates locale and unsubscribes on cleanup', async () => {
  const f = fixture(), seen = []
  const stop = f.api.listenForVosLocale(locale => seen.push(locale))
  const b = bridge(() => ({ locale: 'zh-CN' }))
  f.window.vos_platform = b
  f.tick(); await flush()
  assert.deepEqual(seen, ['zh-CN'])
  b.emit('en-US')
  assert.deepEqual(seen, ['zh-CN', 'en'])
  stop(); b.emit('zh-CN')
  assert.equal(b.listeners.size, 0)
  assert.equal(f.events.size, 0)
  assert.deepEqual(seen, ['zh-CN', 'en'])
})

test('slow initial snapshot cannot overwrite a newer locale event', async () => {
  const f = fixture(), seen = []
  let resolve
  const pending = new Promise(done => { resolve = done })
  const b = bridge(() => pending)
  f.window.vos_platform = b
  const stop = f.api.listenForVosLocale(locale => seen.push(locale))
  await flush(); b.emit('en'); resolve({ locale: 'zh-CN' }); await flush()
  assert.deepEqual(seen, ['en'])
  stop()
})

test('cleanup suppresses a pending snapshot', async () => {
  const f = fixture(), seen = []
  let resolve
  f.window.vos_platform = bridge(() => new Promise(done => { resolve = done }))
  const stop = f.api.listenForVosLocale(locale => seen.push(locale))
  await flush(); stop(); resolve({ locale: 'zh-CN' }); await flush()
  assert.deepEqual(seen, [])
})

test('every literal translation in components has an English entry', () => {
  const catalog = JSON.parse(fs.readFileSync('src/messages.en.json', 'utf8'))
  for (const file of ['App.tsx', 'pages/RulesPage.tsx', 'pages/TestPage.tsx', 'pages/ModelsPage.tsx', 'pages/IntegrationPage.tsx']) {
    const tree = ts.createSourceFile(file, fs.readFileSync(`src/${file}`, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    function visit(node) {
      if (ts.isCallExpression(node) && node.expression.getText(tree) === 't') {
        const key = node.arguments[0]
        if (ts.isStringLiteral(key) || ts.isNoSubstitutionTemplateLiteral(key)) assert.ok(catalog[key.text], `${file}: ${key.text}`)
      }
      ts.forEachChild(node, visit)
    }
    visit(tree)
  }
})
