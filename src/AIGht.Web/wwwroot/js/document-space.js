import * as THREE from '../vendor/three/three.module.js';

let state = null;
let pdfjsPromise;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const ink = '#232522';
export function preferFlat() { return matchMedia('(max-width: 820px), (prefers-reduced-motion: reduce)').matches; }

function pageTexture(page) {
  const canvas = document.createElement('canvas');
  canvas.width = 768; canvas.height = 1086;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 768, 1086);
  ctx.fillStyle = '#687064'; ctx.font = '500 20px "Geist Sans", sans-serif';
  ctx.fillText('AIGht / Source document', 64, 64);
  ctx.fillText(String(page.pageNumber), 670, 64);
  ctx.fillStyle = ink; ctx.font = '400 25px "Geist Sans", sans-serif';
  let y = 140;
  for (const paragraph of page.text.split('\n')) {
    let line = '';
    for (const word of paragraph.split(/\s+/)) {
      const next = line ? `${line} ${word}` : word;
      if (ctx.measureText(next).width > 640 && line) { ctx.fillText(line, 64, y); y += 39; line = word; }
      else line = next;
      if (y > 990) break;
    }
    if (y > 990) break;
    if (line) { ctx.fillText(line, 64, y); y += 39; }
    y += 18;
  }
  if (page.status !== 'readable') {
    ctx.fillStyle = '#FBF3DB'; ctx.fillRect(50, 1000, 668, 44);
    ctx.fillStyle = '#7A3E00'; ctx.font = '500 19px "Geist Sans", sans-serif'; ctx.fillText('Some content could not be read', 65, 1029);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function clearMeshes(s) {
  for (const item of s.items) {
    s.group.remove(item.mesh);
    item.mesh.geometry.dispose();
    for (const material of item.mesh.material) { material.map?.dispose(); material.dispose(); }
  }
  s.items = [];
}

function targets(s) {
  if (!s.renderer) return;
  const total = s.pages.length;
  const start = Math.min(Math.max(0, s.selected - 4), Math.max(0, total - 8));
  const visible = s.pages.slice(start, start + 8);
  const ids = visible.map(p => p.pageNumber).join(',');
  if (ids !== s.visibleIds) {
    clearMeshes(s); s.visibleIds = ids;
    for (const page of visible) {
      const face = new THREE.MeshStandardMaterial({ map: pageTexture(page), roughness: 1, metalness: 0 });
      const sides = Array.from({ length: 4 }, () => new THREE.MeshStandardMaterial({ color: '#E8E5DF', roughness: 1 }));
      const back = new THREE.MeshStandardMaterial({ color: '#FFFFFF', roughness: 1 });
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(1.72, 2.44, 0.018), [...sides, face, back]);
      mesh.userData.page = page.pageNumber;
      mesh.castShadow = true;
      s.group.add(mesh); s.items.push({ mesh, page, target: new THREE.Vector3(), angle: 0 });
    }
    refreshPdfTextures(s, s.epoch);
  }
  visible.forEach((page, index) => {
    const item = s.items[index], offset = index - (visible.length - 1) / 2;
    const selected = page.pageNumber === s.selected;
    item.target.set(offset * (s.spread ? .90 : .57), selected ? .12 : -.025 * Math.abs(offset), selected ? .65 : -.10 * Math.abs(offset));
    item.angle = offset * -.035;
    if (reduced.matches || !s.animate) { item.mesh.position.copy(item.target); item.mesh.rotation.y = item.angle; }
  });
  resize(s);
}

function requestRender(s) {
  if (s.disposed || s.frame || !s.visible || document.hidden || !s.intersecting) return;
  s.frame = requestAnimationFrame(time => frame(s, time));
}

function frame(s, time) {
  s.frame = 0;
  if (s.disposed || !s.visible || document.hidden || !s.intersecting) return;
  const dt = Math.min(.05, (time - (s.lastTime || time)) / 1000);
  s.lastTime = time;
  const alpha = reduced.matches || !s.animate ? 1 : 1 - Math.exp(-18 * Math.max(dt, .016));
  let moving = false;
  for (const item of s.items) {
    item.mesh.position.lerp(item.target, alpha);
    item.mesh.rotation.y += (item.angle - item.mesh.rotation.y) * alpha;
    if (item.mesh.position.distanceToSquared(item.target) > .000002 || Math.abs(item.mesh.rotation.y - item.angle) > .0005) moving = true;
  }
  s.group.rotation.y += (s.turn - s.group.rotation.y) * alpha;
  s.group.rotation.x += (s.pitch - s.group.rotation.x) * alpha;
  moving ||= Math.abs(s.turn - s.group.rotation.y) > .0005 || Math.abs(s.pitch - s.group.rotation.x) > .0005;
  s.renderer.render(s.scene, s.camera);
  if (moving) requestRender(s);
}

function resize(s) {
  const { width, height } = s.host.getBoundingClientRect();
  if (width < 1 || height < 1 || s.disposed) return;
  const ratio = width / height;
  const spreadWidth = (Math.min(8, s.pages.length) - 1) * (s.spread ? .90 : .57) + 2.35;
  const vertical = Math.max(3.7, spreadWidth / ratio);
  s.camera.left = -vertical * ratio / 2; s.camera.right = vertical * ratio / 2;
  s.camera.top = vertical / 2; s.camera.bottom = -vertical / 2;
  s.camera.updateProjectionMatrix();
  s.renderer.setSize(width, height, false);
  requestRender(s);
}

export function initialize(host, dotnet) {
  dispose();
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' }); }
  catch { state = { host, dotnet, pages: [], items: [], epoch: 0, pdf: null, pdfLoading: null, disposed: false, renderer: null }; return false; }
  renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 768 ? 1 : 1.5));
  renderer.setClearColor(0xF7F6F3, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap;
  const scene = new THREE.Scene();
  scene.add(new THREE.AmbientLight(0xffffff, 2.2));
  const light = new THREE.DirectionalLight(0xffffff, 2.4); light.position.set(-3, 6, 6); scene.add(light);
  light.castShadow = true; light.shadow.mapSize.set(1024, 1024);
  Object.assign(light.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6, near: .5, far: 30 });
  light.shadow.bias = -.0005;
  const camera = new THREE.OrthographicCamera(-3, 3, 2, -2, .1, 100);
  camera.position.set(0, .65, 8); camera.lookAt(0, 0, 0);
  const group = new THREE.Group(); group.rotation.x = -.07; group.rotation.y = -.16; scene.add(group);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.MeshStandardMaterial({ color: '#F7F6F3', roughness: 1 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -1.30; scene.add(ground);
  ground.receiveShadow = true;
  host.replaceChildren(renderer.domElement);
  renderer.domElement.setAttribute('aria-hidden', 'true');
  renderer.domElement.style.touchAction = 'pan-y';
  const s = state = { host, renderer, scene, camera, group, ground, dotnet, items: [], pages: [], visibleIds: '', selected: 1, epoch: 0, pdf: null, pdfLoading: null, visible: true, intersecting: true, frame: 0, turn: -.16, pitch: -.07, spread: false, animate: true, disposed: false, drag: null };
  const abort = s.abort = new AbortController();
  const options = { signal: abort.signal };
  const canvas = renderer.domElement;
  canvas.addEventListener('pointerdown', event => {
    if (s.drag || event.button !== 0 || event.pointerType === 'touch') return;
    s.drag = { id: event.pointerId, x: event.clientX, y: event.clientY, initialX: event.clientX, initialY: event.clientY, turn: s.turn, pitch: s.pitch };
    canvas.setPointerCapture(event.pointerId);
  }, options);
  canvas.addEventListener('pointermove', event => {
    if (!s.drag || s.drag.id !== event.pointerId || reduced.matches) return;
    s.turn = Math.max(-.37, Math.min(.05, s.drag.turn + (event.clientX - s.drag.x) * .002));
    s.pitch = Math.max(-.17, Math.min(.03, s.drag.pitch + (event.clientY - s.drag.y) * .001));
    requestRender(s);
  }, options);
  canvas.addEventListener('pointerup', event => {
    const drag = s.drag;
    if (drag && drag.id !== event.pointerId) return;
    const isClick = !drag || Math.hypot(event.clientX - drag.initialX, event.clientY - drag.initialY) < 5;
    s.drag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (!isClick) return;
    const rect = canvas.getBoundingClientRect();
    const pointer = new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    const ray = new THREE.Raycaster(); ray.setFromCamera(pointer, s.camera);
    const hit = ray.intersectObjects(s.items.map(item => item.mesh))[0];
    if (hit) s.dotnet.invokeMethodAsync('SelectPageFromScene', hit.object.userData.page).catch(() => {});
  }, options);
  canvas.addEventListener('pointercancel', () => { s.drag = null; }, options);
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); setVisible(false); s.dotnet.invokeMethodAsync('SceneUnavailable').catch(() => {}); }, options);
  document.addEventListener('visibilitychange', () => { if (document.hidden && s.frame) { cancelAnimationFrame(s.frame); s.frame = 0; } else requestRender(s); }, options);
  reduced.addEventListener('change', () => { s.animate = !reduced.matches; targets(s); }, options);
  s.resize = new ResizeObserver(() => resize(s)); s.resize.observe(host);
  s.intersection = new IntersectionObserver(entries => { s.intersecting = entries[0].isIntersecting; requestRender(s); }); s.intersection.observe(host);
  resize(s);
  return true;
}

async function pdfLibrary() {
  pdfjsPromise ||= import('../vendor/pdfjs/pdf.mjs').then(module => { module.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.mjs'; return module; });
  return pdfjsPromise;
}

export async function setPages(pages, selected, demo, bytes) {
  const s = state;
  if (!s || s.disposed) return;
  s.epoch++; const epoch = s.epoch;
  clearMeshes(s); s.visibleIds = ''; s.pages = pages; s.selected = selected;
  const previous = s.pdfLoading; s.pdfLoading = null; s.pdf = null;
  if (previous) await previous.destroy();
  if (s.disposed || epoch !== s.epoch) return;
  targets(s);
  if (!demo && !bytes) return;
  try {
    const library = await pdfLibrary();
    if (s.disposed || epoch !== s.epoch) return;
    const load = library.getDocument({ ...(demo ? { url: '/examples/scholarship-guidelines.pdf' } : { data: new Uint8Array(bytes).slice() }), cMapUrl: '/vendor/pdfjs/cmaps/', cMapPacked: true, standardFontDataUrl: '/vendor/pdfjs/standard_fonts/', wasmUrl: '/vendor/pdfjs/wasm/', iccUrl: '/vendor/pdfjs/iccs/', isEvalSupported: false, enableXfa: false });
    s.pdfLoading = load;
    const pdf = await load.promise;
    if (s.disposed || epoch !== s.epoch) { await load.destroy(); return; }
    s.pdf = pdf;
    await refreshPdfTextures(s, epoch);
  } catch { /* Canonical text and source controls remain usable if a preview cannot render. */ }
}

async function refreshPdfTextures(s, epoch) {
  if (!s.pdf || !s.renderer) return;
  for (const item of [...s.items]) {
    try {
      const page = await s.pdf.getPage(item.page.pageNumber);
      if (s.disposed || s.epoch !== epoch || !s.items.includes(item)) return;
      const natural = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: Math.min(1.4, 1024 / Math.max(natural.width, natural.height)) });
      const canvas = document.createElement('canvas'); canvas.width = viewport.width; canvas.height = viewport.height;
      await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
      if (s.disposed || s.epoch !== epoch || !s.items.includes(item)) return;
      const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
      item.mesh.material[4].map?.dispose(); item.mesh.material[4].map = texture; item.mesh.material[4].needsUpdate = true;
      requestRender(s);
    } catch { }
  }
}

export function selectPage(page, animate = true) { const s = state; if (!s) return; s.selected = page; s.animate = animate && !reduced.matches; targets(s); }
export function command(command, direction) {
  const s = state; if (!s?.renderer) return; s.animate = !reduced.matches;
  if (command === 'spread') s.spread = true;
  if (command === 'stack') s.spread = false;
  if (command === 'turn' && !reduced.matches) s.turn = Math.max(-.37, Math.min(.05, s.turn + direction * .10));
  if (command === 'reset') { s.turn = -.16; s.pitch = -.07; s.spread = false; }
  targets(s);
}
export function setVisible(visible) {
  const s = state; if (!s?.renderer) return;
  s.visible = visible;
  s.renderer.domElement.style.visibility = visible ? 'visible' : 'hidden';
  if (!visible && s.frame) { cancelAnimationFrame(s.frame); s.frame = 0; }
  if (visible) { resize(s); requestRender(s); }
}
export async function renderPdf(id, number, boxes) {
  const s = state, host = document.getElementById(id);
  if (!s?.pdf || !host) return;
  const epoch = s.epoch, request = s.pdfRenderRequest = (s.pdfRenderRequest || 0) + 1;
  const page = await s.pdf.getPage(number);
  const natural = page.getViewport({ scale: 1 });
  const viewport = page.getViewport({ scale: Math.min(1.5, (host.clientWidth || 600) / natural.width) });
  const canvas = document.createElement('canvas'); canvas.width = viewport.width; canvas.height = viewport.height;
  const context = canvas.getContext('2d');
  await page.render({ canvasContext: context, viewport }).promise;
  if (s.disposed || s.epoch !== epoch || s.pdfRenderRequest !== request || !host.isConnected) return;
  context.fillStyle = 'rgba(52,101,56,.18)';
  for (const [x,y,w,h] of boxes) context.fillRect(x*viewport.width,y*viewport.height,w*viewport.width,h*viewport.height);
  host.replaceChildren(canvas);
}
export function clearPrivateContent() {
  const s = state; if (!s) return;
  s.epoch++; s.pages = []; clearMeshes(s); s.visibleIds = '';
  s.pdfLoading?.destroy().catch(() => {}); s.pdf = null; s.pdfLoading = null;
  document.getElementById('pdf-source')?.replaceChildren();
  s.renderer?.clear();
}
export function dispose() {
  const s = state; if (!s) return;
  clearPrivateContent(); s.disposed = true;
  if (s.frame) cancelAnimationFrame(s.frame);
  s.abort?.abort(); s.resize?.disconnect(); s.intersection?.disconnect();
  s.ground?.geometry.dispose(); s.ground?.material.dispose();
  s.renderer?.dispose(); s.renderer?.forceContextLoss(); s.host.replaceChildren(); state = null;
}
