'use client';

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

/** Content stays readable without JS and for members who prefer less motion. */
export function HomeReveal({ children, className = '' }: { children: ReactNode; className?: string }) {
  const element = useRef<HTMLDivElement>(null);
  const [waiting, setWaiting] = useState(false);
  useEffect(() => {
    const node = element.current;
    if (!node || !('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (node.getBoundingClientRect().top < window.innerHeight * .94) return;
    setWaiting(true);
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { setWaiting(false); observer.disconnect(); }
    }, { threshold: 0, rootMargin: '0px 0px -6% 0px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return <div ref={element} className={`v2-home-reveal ${className}`} data-reveal={waiting ? 'waiting' : 'visible'} onFocusCapture={() => setWaiting(false)}>{children}</div>;
}

export function CollectionOrbit({ children, artwork }: { children: ReactNode; artwork: string[] }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = element.current;
    if (!node) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let visible = true;
    const paint = () => {
      frame = 0;
      if (reduced.matches) { node.style.setProperty('--orbit-scroll', '0deg'); return; }
      const rect = node.getBoundingClientRect();
      const progress = Math.min(1, Math.max(0, (window.innerHeight - rect.top) / (window.innerHeight + rect.height)));
      // Give the artwork a visible sweep around the copy while this section
      // passes through the viewport. Scrolling back reverses the same path.
      node.style.setProperty('--orbit-scroll', `${(progress - .5) * 240}deg`);
    };
    const schedule = () => { if (visible && !frame) frame = window.requestAnimationFrame(paint); };
    const observer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
      visible = entries[0].isIntersecting;
      if (visible) schedule();
    }) : null;
    observer?.observe(node);
    const configure = () => {
      window.cancelAnimationFrame(frame);
      frame = 0;
      window.removeEventListener('scroll', schedule, true);
      window.removeEventListener('resize', schedule);
      if (!reduced.matches) {
        // Capture also handles an embedded page's scrolling container.
        window.addEventListener('scroll', schedule, { passive: true, capture: true });
        window.addEventListener('resize', schedule);
      }
      paint();
    };
    configure();
    reduced.addEventListener('change', configure);
    return () => {
      observer?.disconnect();
      window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', schedule, true);
      window.removeEventListener('resize', schedule);
      reduced.removeEventListener('change', configure);
    };
  }, []);
  return <div ref={element} className="v2-collection-orbit" id="Access">
    <div className="v2-orbit-decoration" aria-hidden="true">
      <div className="v2-orbit-ring inner" /><div className="v2-orbit-ring middle" /><div className="v2-orbit-ring outer" />
      <div className="v2-orbit-track">
        {artwork.map((image, index) => <div className="v2-orbit-position" key={image} style={{ '--orbit-angle': `${index * (360 / artwork.length) + 22}deg`, '--orbit-scale': index % 3 === 0 ? 1.12 : .86 } as CSSProperties}>
          <div className="v2-orbit-card"><img src={image} width={210} height={120} loading="lazy" alt="" /></div>
        </div>)}
      </div>
    </div>
    <div className="v2-collection-copy">{children}</div>
  </div>;
}
