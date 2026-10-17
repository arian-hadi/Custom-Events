/** Rebuild the local replica from its public reference. Never used at runtime. */
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { load } from 'cheerio';

const origin = 'https://playo-128.webflow.io';
const routes = ['/', '/store', '/news', '/contact-us',
  ...['forza-horizon-3','call-of-duty','stickers','accessories','warzone','vr-goggles','sony-ps4','fifa-21'].map(x=>'/product/'+x),
  ...['games','merchandise','hardware-and-discs'].map(x=>'/category/'+x),
  ...['events','games','news'].map(x=>'/news-categories/'+x),
  ...['the-biggest-summer-game-fest','new-details-on-fifa','enhance-player-experience','boost-your-marketing-power','manage-your-games-business','reach-a-global-audience'].map(x=>'/news-posts/'+x)];
const excluded = ['/about-us','/our-team','/pricing','/career','/our-process','/faq','/job-positions/technical-infrastructure','/templates/licensing'];
const assets = new Map();
const jobs = new Map();
await mkdir('public/assets', { recursive: true });
await mkdir('reference', { recursive: true });

async function fetchOK(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r;
}
function assetName(url) {
  const parsed = new URL(url);
  const basename = decodeURIComponent(parsed.pathname.split('/').pop()).replace(/[^a-zA-Z0-9._-]/g,'-');
  return `/assets/${createHash('sha1').update(url).digest('hex').slice(0,10)}-${basename || 'asset'}${url.includes('fonts.googleapis.com/css')?'.css':''}`;
}
async function asset(url) {
  if (!/^https?:/.test(url)) return url;
  if (jobs.has(url)) return jobs.get(url);
  const local = assetName(url);
  assets.set(url, local);
  const job = (async () => {
    const r = await fetchOK(url);
    let buffer;
    if (new URL(url).pathname.endsWith('.css') || url.includes('fonts.googleapis.com/css')) {
      let css = await r.text();
      const refs = [...css.matchAll(/url\((?:"([^"]+)"|'([^']+)'|([^)]*))\)/g)].map(x=>x[1]||x[2]||x[3]).filter(x=>!x.startsWith('data:'));
      await Promise.all([...new Set(refs)].map(async ref=> {const loc=await asset(new URL(ref,url).href);css=css.split(ref).join(loc);}));
      buffer=css;
    } else buffer = Buffer.from(await r.arrayBuffer());
    await writeFile(path.join('public',local),buffer);
    return local;
  })();
  jobs.set(url, job);
  return job;
}

// Freeze the exact Google Fonts stylesheets and their font files locally.
const fontURL='https://fonts.googleapis.com/css?family=Lato:100,100italic,300,300italic,400,400italic,700,700italic,900,900italic%7CBitter:400,700,400italic%7COpen+Sans:300,300italic,400,400italic,600,600italic,700,700italic,800,800italic%7CSpace+Grotesk:regular,700';
const fonts = await asset(fontURL);
const products=[];
for (const route of routes) {
  const raw = await (await fetchOK(origin+route)).text();
  await writeFile(path.join('reference',route==='/'?'home.html':route.slice(1).replaceAll('/','--')+'.html'),raw);
  const $ = load(raw);
  $('html').removeAttr('data-wf-domain');
  $('title').text(route==='/'?'Playo — Play, Improve & Win':$('title').text().replace(/\s*[-–|]\s*Webflow.*$/i,''));
  $('meta[name="generator"], link[rel="preconnect"]').remove();
  $('script').each((i,e)=> {
    const el=$(e), src=el.attr('src')||'', code=el.text();
    if (/googletagmanager|google-analytics|webfont/.test(src) || /gtag\(|WebFont\.load/.test(code)) el.remove();
  });
  $('head').append(`<link rel="stylesheet" href="${fonts}"><link rel="stylesheet" href="/replica.css">`);
  // Preserve its layout and typography, but Pages is intentionally inert.
  $('.nav-dropdown').each((i,e)=> {
    $(e).replaceWith('<div class="nav-dropdown"><button type="button" class="nav-dropdown-toggle w-dropdown-toggle pages-dummy" aria-disabled="true"><span class="nav-drop-content"><span>Pages</span><span class="arrow-bottom-drop" aria-hidden="true">arrow_drop_down</span></span></button></div>');
  });
  // Replace template commerce wiring with a local cart; no reference-site API calls.
  $('[data-node-type]').each((i,e)=> {
    const el=$(e); el.attr('data-replica-node',el.attr('data-node-type')).removeAttr('data-node-type');
  });
  $('[data-wf-cart-query], [data-wf-bindings], [data-wf-collection], [data-wf-template-id]').each((i,e)=>{
    for(const name of ['data-wf-cart-query','data-wf-bindings','data-wf-collection','data-wf-template-id']) $(e).removeAttr(name);
  });
  $('script[type="text/x-wf-template"]').remove();
  $('form').attr('action','#').removeAttr('data-wf-page-id').removeAttr('data-wf-element-id');
  $('form').each((i,e)=> {
    const el=$(e); if(!el.is('[data-replica-node="commerce-add-to-cart-form"], [data-replica-node="commerce-cart-form"]')) el.attr('data-local-form','true');
  });
  $('a[href]').each((i,e)=> {
    const el=$(e); let href=el.attr('href');
    if(href.startsWith(origin)) href=href.slice(origin.length)||'/';
    if(excluded.includes(href)) {
      if(el.text().includes('Learn More')) href='/#Access';
      else { href='#'; el.attr('data-dummy','true'); }
    }
    if(href==='/checkout') {href='#';el.attr('data-demo-checkout','true');}
    el.attr('href',href);
  });
  $('[data-replica-node="commerce-cart-container-wrapper"]').attr('data-cart-overlay','');
  $('[data-replica-node="commerce-cart-form"]').remove();
  $('.w-commerce-commercecartemptystate').replaceWith('<div class="replica-cart-items"></div><div class="replica-cart-summary"></div>');
  $('.w-commerce-commercecarterrorstate').remove();
  // Remove vendor advertisements, while retaining the reference footer attribution.
  $('.promotion-labels-wrapper, [class*="buy-this-template"], [class*="more-template"], .w-webflow-badge').remove();
  const remote = new Set();
  const attrs=['src','href','poster','srcset','style'];
  $('*').each((i,e)=> {
    const el=$(e);
    for(const attr of attrs) {
      const val=el.attr(attr); if(!val) continue;
      if(attr==='href'&&!el.is('link'))continue;
      if (attr==='srcset') {for(const part of val.split(',')) {const url=part.trim().split(/\s/)[0];if(/^https?:/.test(url))remote.add(url);}}
      else if(attr==='style') {for(const match of val.matchAll(/url\((?:"([^"]+)"|'([^']+)'|([^)]*))\)/g)){const url=match[1]||match[2]||match[3];if(/^https?:/.test(url))remote.add(url);}}
      else if(/^https?:/.test(val)) remote.add(val);
    }
  });
  await Promise.all([...remote].map(url=>asset(url)));
  // Lightbox images are also declared inside JSON rather than image elements.
  const lightboxes=$('script.w-json').toArray();
  for(const el of lightboxes) {
    let json=$(el).text();
    const urls=[...json.matchAll(/https?:\/\/[^"\s]+/g)].map(m=>m[0]);
    for(const url of urls) json=json.split(url).join(await asset(url));
    $(el).text(json);
  }
  $('*').each((i,e)=> {
    const el=$(e);
    for(const attr of attrs) {
      let val=el.attr(attr); if(!val) continue;
      if(attr==='href'&&!el.is('link'))continue;
      for(const [url,local] of assets) val=val.split(url).join(local);
      el.attr(attr,val);
    }
  });
  $('script[src]').removeAttr('integrity').removeAttr('crossorigin');
  $('img').each((i,e)=> {if(!$(e).attr('alt'))$(e).attr('alt','');});
  if(route.startsWith('/product/')) {
    const name=$('h1').first().text();
    const price=$('.shop-details-price-wrapper').first().text();
    const image=$('.shop-details-image').first().attr('src');
    const sku=$('[data-replica-node="commerce-add-to-cart-form"]').first().attr('data-commerce-sku-id');
    products.push({route,name,sku,price,image:assets.get(image)||image});
    $('body').attr('data-product',route);
  }
  $('body').append('<script src="/replica.js"></script>');
  const output=route==='/'?'index.html':path.join('public',route,'index.html');
  await mkdir(path.dirname(output),{recursive:true});
  await writeFile(output,$.html());
  console.log(`Created ${route}`);
}
await writeFile('public/products.json',JSON.stringify(products,null,2));
await writeFile('reference/routes.json',JSON.stringify(routes,null,2));
await writeFile('reference/assets.json',JSON.stringify(Object.fromEntries(assets),null,2));
console.log(`${routes.length} pages, ${assets.size} localized assets`);
