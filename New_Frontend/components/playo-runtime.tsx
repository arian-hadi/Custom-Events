'use client';
import {useEffect} from 'react';

const scripts=[
  '/assets/2d7ef0ae28-jquery-3.5.1.min.dc5e7f18c8.js',
  '/assets/709fb943c2-webflow.df4022e3b15d6128d173455046a70c84.js',
  '/replica.js',
];
let runtime: Promise<void>|undefined;
function loadScript(src:string) {
  return new Promise<void>((resolve,reject)=>{
    const script=document.createElement('script');
    script.src=src;script.async=true;
    script.onload=()=>resolve();script.onerror=()=>reject(new Error(`Unable to load ${src}`));
    document.body.appendChild(script);
  });
}
export function PlayoRuntime({pageId,bodyClassName,product}:{pageId:string;bodyClassName:string;product:string}) {
  useEffect(()=>{
    document.documentElement.dataset.wfPage=pageId;
    document.body.className=`${bodyClassName} tw:bg-black tw:text-white`;
    if(product)document.body.dataset.product=product;
    document.documentElement.classList.add('w-mod-js');
    if('ontouchstart' in window)document.documentElement.classList.add('w-mod-touch');
    runtime??=(async()=>{
      for(const src of scripts)await loadScript(src);
      requestAnimationFrame(()=>document.dispatchEvent(new Event('IX2_PAGE_UPDATE')));
    })();
    runtime.catch(error=>console.error('Playo interactions:',error));
  },[pageId,bodyClassName,product]);
  return null;
}
