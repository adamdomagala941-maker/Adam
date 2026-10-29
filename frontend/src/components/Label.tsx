import { useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import './Label.css';

export type LabelData = {
  name: string;
  cas: string;
  ec: string;
  formula: string;
  molarMass: string;
  volume: string;
  catalogNumber: string;
  signalWord: string;
  hazards: string;
  precautions: string;
  supplemental: string;
  pictograms: string[];
};

export type LabelFit = { overflow: boolean; minFont: number };

type Props = {
  data: LabelData;
  qrDataUrl: string;
  onFitChange?: (fit: LabelFit) => void;
};

/** Fit against physical layout dimensions, independent of preview scaling. */
function useFit(root: React.RefObject<HTMLDivElement | null>, contents: string, onFitChange?: Props['onFitChange']) {
  const [fontReady, setFontReady] = useState(false);
  useLayoutEffect(() => {
    let live = true;
    document.fonts.ready.then(() => { if (live) setFontReady(true); });
    return () => { live = false; };
  }, []);
  useLayoutEffect(() => {
    const container = root.current;
    if (!container) return;
    const fit = () => {
      let overflow = false;
      let smallest = Infinity;
      container.querySelectorAll<HTMLElement>('[data-fit]').forEach((box) => {
        const text = box.firstElementChild as HTMLElement;
        const max = Number(box.dataset.max || 10);
        const min = Number(box.dataset.min || 3);
        const fits = (size: number) => {
          text.style.fontSize = `${size}pt`;
          return text.scrollHeight <= box.clientHeight && text.scrollWidth <= box.clientWidth;
        };
        let low = min, high = max;
        if (!fits(min)) overflow = true;
        else if (fits(max)) low = max;
        else {
          for (let i = 0; i < 12; i++) {
            const mid = (low + high) / 2;
            if (fits(mid)) low = mid; else high = mid;
          }
        }
        text.style.fontSize = `${low}pt`;
        box.dataset.fontSize = low.toFixed(2);
        box.dataset.overflow = String(text.scrollHeight > box.clientHeight || text.scrollWidth > box.clientWidth);
        if (text.textContent?.trim()) smallest = Math.min(smallest, low);
      });
      onFitChange?.({ overflow, minFont: Number.isFinite(smallest) ? Math.round(smallest * 100) / 100 : 5 });
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(container);
    window.addEventListener('beforeprint', fit);
    return () => { observer.disconnect(); window.removeEventListener('beforeprint', fit); };
  }, [root, contents, fontReady, onFitChange]);
}

function Fit({ className = '', max, min = 3, children }: {
  className?: string; max: number; min?: number; children: ReactNode;
}) {
  return <div className={`label-fit ${className}`} data-fit data-max={max} data-min={min}><div>{children}</div></div>;
}

export default function Label({ data, qrDataUrl, onFitChange }: Props) {
  const root = useRef<HTMLDivElement>(null);
  useFit(root, JSON.stringify(data), onFitChange);
  const pictograms = [...new Set(data.pictograms)].filter((id) => /^GHS0[1-9]$/.test(id));
  const templateGhs = pictograms.length === 3 && ['GHS02', 'GHS05', 'GHS07'].every((id) => pictograms.includes(id));
  const statements = [data.hazards, data.precautions, data.supplemental].filter(Boolean).join('\n');
  const formula = [data.formula, data.molarMass].filter(Boolean).join(' - ');
  return <div ref={root} className="label-pair" aria-label="Etykieta: dwie strony 76 na 51 milimetrów">
    <section className="chemical-label label-front" aria-label="Pierwsza strona etykiety">
      <img className="label-logo" src="/template/label_logo.png" alt="DJCHEM Chemicals Poland S.A." />
      <Fit className="label-cas" max={10}>CAS : {data.cas}</Fit>
      <Fit className="label-ec" max={10}>WE&nbsp; : {data.ec}</Fit>
      <Fit className="label-name" max={14} min={5}>{data.name.toLocaleUpperCase('pl')}</Fit>
      <Fit className="label-formula" max={12} min={5}>{formula}</Fit>
      <Fit className="label-volume" max={12} min={5}>{data.volume}</Fit>
      {qrDataUrl && <img className="label-qr" src={qrDataUrl} alt={`Kod QR: ${data.catalogNumber}`} />}
      <Fit className="label-catalog" max={6}>{data.catalogNumber}</Fit>
    </section>
    <section className="chemical-label label-back" aria-label="Druga strona etykiety">
      <Fit className="label-statements" max={5} min={2.5}>{statements}</Fit>
      <div className={`label-pictograms ${templateGhs ? 'template-ghs' : ''}`} data-count={pictograms.length}>
        {templateGhs
          ? <img src="/template/current_ghs.png" alt="GHS02: płomień; GHS07: wykrzyknik; GHS05: działanie żrące" />
          : pictograms.map((id) => <img key={id} src={`/template/${id}.svg`} alt={id} />)}
      </div>
      <Fit className="label-signal" max={7.5} min={3}>{data.signalWord.toLocaleUpperCase('pl')}</Fit>
    </section>
  </div>;
}
