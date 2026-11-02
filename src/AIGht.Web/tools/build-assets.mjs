import assert from 'node:assert/strict';
import { copyFile, cp, mkdir, readFile, readdir, stat, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const project = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const modules = join(project, 'node_modules');
const web = join(project, 'wwwroot');
const vendor = join(web, 'vendor');
const fonts = join(web, 'fonts');

async function copy(source, destination) {
  await mkdir(dirname(destination), { recursive: true });
  await copyFile(source, destination);
}

async function copyText(source, destination) {
  await mkdir(dirname(destination), { recursive: true });
  // npm package text can use CRLF; generated text must match Linux Git checkouts.
  await writeFile(destination, (await readFile(source, 'utf8')).replace(/\r\n?/g, '\n'));
}

async function copyTree(source, destination) {
  await mkdir(destination, { recursive: true });
  await cp(source, destination, { recursive: true });
}

const packages = {};
for (const name of ['three', 'pdfjs-dist', 'bootstrap', '@fontsource/geist-sans', '@fontsource/instrument-serif', '@phosphor-icons/core']) {
  packages[name] = JSON.parse(await readFile(join(modules, name, 'package.json'), 'utf8'));
}

for (const file of ['three.module.js', 'three.core.js']) {
  await copyText(join(modules, 'three', 'build', file), join(vendor, 'three', file));
}
await copyText(join(modules, 'three', 'LICENSE'), join(vendor, 'three', 'LICENSE'));

for (const file of ['pdf.mjs', 'pdf.worker.mjs']) {
  await copyText(join(modules, 'pdfjs-dist', 'build', file), join(vendor, 'pdfjs', file));
}
for (const directory of ['cmaps', 'standard_fonts', 'wasm', 'iccs']) {
  await copyTree(join(modules, 'pdfjs-dist', directory), join(vendor, 'pdfjs', directory));
}
await copyText(join(modules, 'pdfjs-dist', 'LICENSE'), join(vendor, 'pdfjs', 'LICENSE'));

await copyText(join(modules, 'bootstrap', 'dist', 'css', 'bootstrap.min.css'), join(vendor, 'bootstrap', 'bootstrap.min.css'));
await copyText(join(modules, 'bootstrap', 'LICENSE'), join(vendor, 'bootstrap', 'LICENSE'));

const fontFaces = [];
for (const weight of [400, 500, 600]) {
  const file = `geist-sans-latin-${weight}-normal.woff2`;
  await copy(join(modules, '@fontsource', 'geist-sans', 'files', file), join(fonts, file));
  fontFaces.push(`@font-face { font-family: 'Geist Sans'; font-style: normal; font-weight: ${weight}; font-display: swap; src: url('./${file}') format('woff2'); }`);
}
const serifFile = 'instrument-serif-latin-400-normal.woff2';
await copy(join(modules, '@fontsource', 'instrument-serif', 'files', serifFile), join(fonts, serifFile));
fontFaces.push(`@font-face { font-family: 'Instrument Serif'; font-style: normal; font-weight: 400; font-display: swap; src: url('./${serifFile}') format('woff2'); }`);
await writeFile(join(fonts, 'fonts.css'), `${fontFaces.join('\n')}\n`);
await copyText(join(modules, '@fontsource', 'geist-sans', 'LICENSE'), join(fonts, 'GEIST-LICENSE.txt'));
await copyText(join(modules, '@fontsource', 'instrument-serif', 'LICENSE'), join(fonts, 'INSTRUMENT-SERIF-LICENSE.txt'));

const iconNames = [
  'arrow-left', 'arrow-right', 'arrow-counter-clockwise', 'arrows-out-simple',
  'arrows-in-simple', 'book-open', 'caret-down', 'chat-circle-text', 'check',
  'check-circle', 'cube', 'file-pdf', 'link-simple', 'magnifying-glass-plus',
  'magnifying-glass-minus', 'spinner-gap', 'text-t', 'trash', 'upload-simple',
  'warning-circle', 'x',
];
const symbols = [];
for (const name of iconNames) {
  for (const weight of ['regular', 'bold', 'fill']) {
    const svg = await readFile(join(modules, '@phosphor-icons', 'core', 'assets', weight, `${name}${weight === 'regular' ? '' : `-${weight}`}.svg`), 'utf8');
    const viewBox = svg.match(/viewBox="([^"]+)"/)?.[1];
    assert.equal(viewBox, '0 0 256 256', `Unexpected viewBox for ${name}`);
    const paths = svg.replace(/^[\s\S]*?<svg\b[^>]*>/, '').replace(/<\/svg>\s*$/, '');
    symbols.push(`<symbol id="${name}-${weight}" viewBox="0 0 256 256" fill="currentColor">${paths}</symbol>`);
  }
}
await mkdir(join(vendor, 'icons'), { recursive: true });
await writeFile(join(vendor, 'icons', 'phosphor.svg'), `<svg xmlns="http://www.w3.org/2000/svg">\n${symbols.join('\n')}\n</svg>\n`);
await copyText(join(modules, '@phosphor-icons', 'core', 'LICENSE'), join(vendor, 'icons', 'LICENSE'));

const manifest = {
  generated_by: 'npm run assets',
  packages: Object.fromEntries(Object.entries(packages).map(([name, value]) => [name, { version: value.version, license: value.license }])),
  imports: {
    three: 'vendor/three/three.module.js',
    pdfjs: 'vendor/pdfjs/pdf.mjs',
    pdfjs_worker: 'vendor/pdfjs/pdf.worker.mjs',
    bootstrap_css: 'vendor/bootstrap/bootstrap.min.css',
    fonts_css: 'fonts/fonts.css',
    icons: 'vendor/icons/phosphor.svg',
  },
  icons: iconNames,
  icon_weights: ['regular', 'bold', 'fill'],
};
await writeFile(join(vendor, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
const notices = [
  '# AIGht self-hosted third-party assets',
  '',
  'Generated from the exact versions in package-lock.json by npm run assets.',
  'These assets are served locally. No runtime CDN or font-service requests are required.',
  '',
  ...Object.entries(packages).map(([name, value]) => `- ${name} ${value.version}: ${value.license}`),
  '',
  'License texts are retained beside the corresponding libraries and in ../fonts/.',
  'The PDF.js support directories retain their bundled notices and licenses.',
  'The Phosphor sprite contains selected unmodified icon paths, grouped into symbols.',
  '',
].join('\n');
await writeFile(join(vendor, 'THIRD-PARTY-NOTICES.md'), notices);

const threeSource = await readFile(join(vendor, 'three', 'three.module.js'), 'utf8');
assert(threeSource.includes("from './three.core.js'"), 'Three.js core import changed; update the copy strategy.');
const requiredFiles = [...Object.values(manifest.imports), 'vendor/three/three.core.js'];
for (const file of requiredFiles) {
  const info = await stat(join(web, file));
  assert(info.size > 0, `Missing or empty output: ${file}`);
}
async function bytes(directory) {
  let total = 0;
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    total += entry.isDirectory() ? await bytes(path) : (await stat(path)).size;
  }
  return total;
}
console.log(JSON.stringify({ packages: manifest.packages, vendor_bytes: await bytes(vendor), font_bytes: await bytes(fonts), icon_symbols: symbols.length }, null, 2));

