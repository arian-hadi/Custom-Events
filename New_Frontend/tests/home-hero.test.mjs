import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import Module, { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from 'cheerio';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
function component(path) {
  const filename = resolve(root, path);
  const result = new Module(filename);
  const require = createRequire(filename);
  result.require = name => name === '@/lib/api' ? component('lib/api.ts') : require(name);
  result._compile(ts.transpileModule(readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, filename);
  return result.exports;
}
const { HomeHero } = component('components/platform/home-hero.tsx');
const site = { name: 'Custom community', hero_title: 'Admin heading', hero_subtitle: 'Admin introduction',
  hero_button_text: 'Browse', hero_button_url: '/store', hero_image: '/media/site/hero/custom.png' };
const render = (props = {}) => load(renderToStaticMarkup(createElement(HomeHero, { site, loading: false, ...props })));

test('pending settings never render or request fallback artwork or premature hero copy', () => {
  const $ = render({ loading: true });
  assert.equal($('img').length, 0);
  assert.equal($('h1').length, 0);
  assert.equal($('[role="status"]').text(), 'Loading homepage…');
  assert.equal($('section').attr('data-content-ready'), 'false');
  assert.equal($('section').attr('data-art-ready'), 'false');
});

test('configured copy appears while the actual artwork waits for its load event', () => {
  const $ = render();
  assert.equal($('h1').text(), site.hero_title);
  assert.equal($('img').attr('src'), site.hero_image);
  assert.equal($('section').attr('data-content-ready'), 'true');
  assert.equal($('section').attr('data-art-ready'), 'false');
  assert.equal($('img').length, 1);
  assert.doesNotMatch($.html(), /Group-28|Spider-Man/);
});

test('missing or invalid configured artwork uses a neutral placeholder without requesting a demo image', () => {
  for (const hero_image of ['', 'javascript:alert(1)']) {
    const $ = render({ site: { ...site, hero_image } });
    assert.equal($('img').length, 0);
    assert.equal($('.v2-hero-art-placeholder').text(), 'TF');
    assert.equal($('section').attr('data-art-ready'), 'true');
    assert.equal($('h1').text(), site.hero_title);
  }
});
