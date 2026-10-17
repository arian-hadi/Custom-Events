import {readFileSync, existsSync} from 'node:fs';
import {join} from 'node:path';
import {load} from 'cheerio';
const routes=JSON.parse(readFileSync('reference/routes.json','utf8'));
const failures=[];
let resources=0;
for(const route of routes) {
  const file=join('reference/rendered',route==='/'?'home.html':route.slice(1).replaceAll('/','--')+'.html');
  const $=load(readFileSync(file,'utf8'));
  if(!$('h1').length)failures.push(`${route}: missing main heading`);
  if($('.pages-dummy').length!==1||$('.w-nav .w-dropdown').length)failures.push(`${route}: Pages must be dummy`);
  if($('script[src*="googletagmanager"]').length)failures.push(`${route}: tracking script present`);
  $('[src],link[href]').each((i,e)=>{
    const source=$(e).attr('src')||$(e).attr('href');
    if(!source||source.startsWith('data:'))return;
    if(source.startsWith('/')) {resources++;if(!existsSync(join('public',source)))failures.push(`${route}: missing ${source}`);}
    else if(/^https?:/.test(source))failures.push(`${route}: external resource ${source}`);
  });
  $('a[href]').each((i,e)=>{
    const href=$(e).attr('href');if(!href.startsWith('/'))return;
    const target=href.split(/[?#]/)[0]||'/';
    if(!routes.includes(target))failures.push(`${route}: missing route ${target}`);
  });
  const response=await fetch('http://localhost:5173'+route);
  if(!response.ok)failures.push(`${route}: HTTP ${response.status}`);
  const rendered=await response.text();
  if(!rendered.includes('/_next/'))failures.push(`${route}: not rendered by Next.js`);
}
const catalog=JSON.parse(readFileSync('public/products.json','utf8'));
for(const p of catalog)if(!p.name||!p.sku||!p.price||!existsSync(join('public',p.image||'missing')))failures.push(`Incomplete product ${p.route}`);
if(failures.length){console.error(failures.join('\n'));process.exit(1);}
console.log(`Verified ${routes.length} pages, ${resources} resource references, 8 cart products and all internal links.`);
