/** Converts the verified reference documents into editable React components. */
import { readFileSync, writeFileSync, mkdirSync, renameSync, existsSync } from 'node:fs';
import path from 'node:path';
import {load} from 'cheerio';

const routes=JSON.parse(readFileSync('reference/routes.json','utf8'));
const assets=JSON.parse(readFileSync('reference/assets.json','utf8'));
mkdirSync('components/generated',{recursive:true});
mkdirSync('reference/rendered',{recursive:true});
mkdirSync('app',{recursive:true});
const aliases={class:'className',for:'htmlFor',tabindex:'tabIndex',srcset:'srcSet',maxlength:'maxLength',inputmode:'inputMode',charset:'charSet','fill-rule':'fillRule','stroke-width':'strokeWidth'};
const voids=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
const styleObject=value=>Object.fromEntries(value.split(';').filter(s=>s.includes(':')).map(rule=>{const pos=rule.indexOf(':');let key=rule.slice(0,pos).trim();key=key.startsWith('--')?key:key.replace(/-([a-z])/g,(_,c)=>c.toUpperCase()).replace(/^Ms/,'ms');return[key,rule.slice(pos+1).trim()];}));
const extras={
  'w-container':'tw:mx-auto',
  'pages-dummy':'tw:cursor-default tw:border-0 tw:bg-transparent',
  'nav-drop-content':'tw:flex tw:items-center',
  'primary-button':'tw:cursor-pointer',
  'secondary-button':'tw:cursor-pointer',
  'footer-email-input':'tw:outline-none',
  'contacts-input':'tw:outline-none',
  'contacts-textarea':'tw:outline-none',
};
function jsx(node) {
  if(node.type==='text')return node.data?'{'+JSON.stringify(node.data)+'}':'';
  if(node.type==='comment')return '';
  if(!node.name)return '';
  if(node.name==='script') {
    if(!node.attribs.class?.includes('w-json'))return '';
    return `<script type="application/json" className="w-json" dangerouslySetInnerHTML={{__html:${JSON.stringify(node.children.map(c=>c.data||'').join(''))}}} />`;
  }
  const attrs=Object.entries(node.attribs||{}).map(([name,val])=>{
    if(name==='style')return `style={${JSON.stringify(styleObject(val))}}`;
    if(name==='class') {const utility=val.split(/\s+/).map(c=>extras[c]||'').filter(Boolean).join(' ');return `className=${JSON.stringify(val+(utility?' '+utility:''))}`;}
    if(name==='value'&&(node.name==='input'||node.name==='textarea')&&node.attribs.type!=='submit')name='defaultValue';
    if(['tabindex','maxlength'].includes(name))return `${aliases[name]}={${Number(val)}}`;
    if(['required','disabled','multiple','checked','readOnly','autoFocus'].includes(name))return `${name}={true}`;
    return `${aliases[name]||name}=${JSON.stringify(val)}`;
  }).join(' ');
  return `<${node.name}${attrs?' '+attrs:''}${voids.has(node.name)?' />':'>'+node.children.map(jsx).join('')+`</${node.name}>`}`;
}
const infos=[];
routes.forEach((route,i)=> {
  const old=route==='/'?'index.html':path.join('public',route,'index.html');
  const cached=path.join('reference/rendered',route==='/'?'home.html':route.slice(1).replaceAll('/','--')+'.html');
  const source=existsSync(old)?old:cached;
  const $=load(readFileSync(source,'utf8'));
  const title=route.startsWith('/product/')?$('h1').first().text()+' — Playo':$('title').text();
  const info={route,title,pageId:$('html').attr('data-wf-page'),siteId:$('html').attr('data-wf-site'),bodyClassName:$('body').attr('class')||'',product:$('body').attr('data-product')||'',initialStyles:$('head style').map((i,e)=>$(e).text()).get().join('\n')};
  infos.push(info);
  const contents=$('body').contents().toArray().map(jsx).join('\n');
  writeFileSync(`components/generated/page-${i}.tsx`,`/* Reference ${route}. Regenerate with npm run convert-reference. */\nexport default function Page${i}() {\nreturn <>\n${contents}\n</>;\n}\n`);
  if(source===old)renameSync(old,cached);
});
writeFileSync('lib/site-pages.ts',routes.map((_,i)=>`import Page${i} from '@/components/generated/page-${i}';`).join('\n')+'\nexport const sitePages = {\n'+infos.map((info,i)=>`${JSON.stringify(info.route)}: { ...${JSON.stringify(info)}, Component: Page${i} },`).join('\n')+'\n};\nexport type SiteRoute = keyof typeof sitePages;\nexport function getSitePage(route: string) { return sitePages[route as SiteRoute]; }\n');
const cssPath=Object.values(assets).find(x=>x.includes('webflow')&&x.endsWith('.css'));
writeFileSync('app/reference.css',readFileSync('public'+cssPath,'utf8'));
writeFileSync('app/replica.css',readFileSync('public/replica.css','utf8'));
const fontPath=Object.values(assets).find(x=>x.endsWith('-css.css'));
writeFileSync('app/fonts.css',readFileSync('public'+fontPath,'utf8'));
console.log(`Converted ${infos.length} routes to Next.js React components.`);
