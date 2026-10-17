/* Local interactions for the replica. Published Webflow handles presentation. */
(() => {
  const key = 'playo-demo-cart-v1';
  let cart = [];
  try {const saved=JSON.parse(localStorage.getItem(key)||'[]'); if(Array.isArray(saved))cart=saved.filter(p=>p&&typeof p.sku==='string'&&Number.isFinite(p.quantity)&&p.quantity>0);} catch {}
  const catalog = fetch('/products.json').then(r=>r.json());
  const overlay = document.querySelector('[data-cart-overlay]');
  let previousFocus;
  const money=n=>'$ '+n.toFixed(2)+' USD';
  const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function save() {try {localStorage.setItem(key,JSON.stringify(cart));}catch{}render();}
  function render() {
    document.querySelectorAll('.cart-quantity').forEach(el=>{el.textContent=String(cart.reduce((n,p)=>n+p.quantity,0));});
    const list=document.querySelector('.replica-cart-items');
    const summary=document.querySelector('.replica-cart-summary');
    if(!list||!summary)return;
    list.innerHTML=cart.length?cart.map(p=>`<div class="replica-cart-row"><img src="${escape(p.image)}" alt="${escape(p.name)}"><div><p><a href="${escape(p.route)}">${escape(p.name)}</a></p><p>${money(p.amount)}</p><button type="button" data-remove="${escape(p.sku)}" aria-label="Remove ${escape(p.name)}">Remove</button></div><input type="number" min="1" max="99" value="${p.quantity}" data-quantity="${escape(p.sku)}" aria-label="Quantity for ${escape(p.name)}"></div>`).join(''):'<p class="replica-empty-cart">No items found.</p>';
    summary.innerHTML=cart.length?`<div class="replica-cart-total"><span>Subtotal</span><strong>${money(cart.reduce((n,p)=>n+p.amount*p.quantity,0))}</strong></div><button type="button" data-demo-checkout>Continue to Checkout</button><p class="replica-cart-status" aria-live="polite"></p>`:'';
  }
  function openCart() {
    if(!overlay)return;
    previousFocus=document.activeElement;
    render();overlay.classList.add('is-open');overlay.setAttribute('aria-hidden','false');
    document.body.style.overflow='hidden';
    overlay.querySelector('[data-replica-node="commerce-cart-close-link"]')?.focus();
  }
  function closeCart() {overlay?.classList.remove('is-open');overlay?.setAttribute('aria-hidden','true');document.body.style.overflow='';previousFocus?.focus();}
  document.addEventListener('click',event=> {
    const target=event.target.closest('a,button,[data-cart-overlay]');
    if(!target)return;
    if(target.matches('.pages-dummy,[data-dummy]')) {event.preventDefault();event.stopImmediatePropagation();return;}
    if(target.matches('[data-replica-node="commerce-cart-open-link"]')) {event.preventDefault();event.stopImmediatePropagation();openCart();}
    if(target.matches('[data-replica-node="commerce-cart-close-link"]')||event.target===overlay) {event.preventDefault();closeCart();}
    if(target.matches('[data-remove]')) {cart=cart.filter(p=>p.sku!==target.dataset.remove);save();}
    if(target.matches('[data-demo-checkout]')) {event.preventDefault();const status=document.querySelector('.replica-cart-status');if(status)status.textContent='This is a demo store. Checkout and payments are not enabled.';else openCart();}
  },true);
  document.addEventListener('change',event=> {
    if(!event.target.matches('[data-quantity]'))return;
    const item=cart.find(p=>p.sku===event.target.dataset.quantity);
    if(item){item.quantity=Math.max(1,Math.min(99,Math.floor(Number(event.target.value)||1)));save();}
  });
  document.addEventListener('submit',async event=> {
    const form=event.target;
    event.preventDefault();event.stopImmediatePropagation();
    if(!form.reportValidity())return;
    if(form.matches('[data-replica-node="commerce-add-to-cart-form"]')) {
      const product=(await catalog).find(p=>p.sku===form.dataset.commerceSkuId);
      if(!product)return;
      const quantity=Math.max(1,Math.min(99,Math.floor(Number(form.querySelector('input[type=number]')?.value)||1)));
      const existing=cart.find(p=>p.sku===product.sku);
      if(existing)existing.quantity=Math.min(99,existing.quantity+quantity);
      else cart.push({...product,quantity,amount:Number(product.price.replace(/[^\d.]/g,''))});
      save();openCart();return;
    }
    if(form.matches('[data-local-form]')) {
      const wrap=form.closest('.w-form');
      const success=wrap?.querySelector('.w-form-done');
      if(success){form.style.display='none';success.style.display='block';success.setAttribute('role','status');success.textContent='Thank you! Your demo submission has been received. No information was sent.';}
    }
  },true);
  document.addEventListener('keydown',event=> {
    if(!overlay?.classList.contains('is-open'))return;
    if(event.key==='Escape')closeCart();
    if(event.key==='Tab') {
      const controls=[...overlay.querySelectorAll('a[href],button,input')].filter(el=>el.getClientRects().length);
      const first=controls[0],last=controls.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
  });
  document.querySelectorAll('input:not([type="submit"]),textarea').forEach(el=>{
    if(!el.getAttribute('aria-label')&&!document.querySelector(`label[for="${el.id}"]`)) el.setAttribute('aria-label',el.placeholder||el.name||'Quantity');
    if(el.type==='number')el.max='99';
  });
  render();
})();
