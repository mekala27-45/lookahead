import type { ReactNode } from "react";

/** A page opens with the question it answers, in the display face, and the answer under it. */
export function PageHeader({ kicker, question, children }: { kicker: string; question: string; children: ReactNode }) {
  return (
    <header className="mb-10">
      <p className="text-xs uppercase tracking-[0.14em] text-ink2 mb-2">{kicker}</p>
      <h1 className="text-[2rem] sm:text-[2.6rem] leading-[1.08] mb-4 max-w-[26ch]">{question}</h1>
      <div className="prose text-[1.05rem] leading-relaxed text-ink space-y-3">{children}</div>
    </header>
  );
}

export function Section({ title, intro, children, id }: { title: string; intro?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="mt-12" aria-labelledby={id} id={id ? `${id}-section` : undefined}>
      <h2 id={id} className="text-[1.6rem] leading-tight mb-2">
        {title}
      </h2>
      {intro ? <div className="prose text-ink2 mb-5 space-y-2">{intro}</div> : null}
      {children}
    </section>
  );
}

export function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">{children}</div>;
}

/** Every page ends here: the objection a load desk lead would raise, and what the build did about it. */
export function Pushback({ children }: { children: ReactNode }) {
  return (
    <section className="mt-14 pt-6 border-t border-hairline" aria-labelledby="pushback" data-testid="pushback">
      <h2 id="pushback" className="text-[1.6rem] leading-tight mb-3">
        What the operator would push back on
      </h2>
      <div className="prose text-[1.02rem] leading-relaxed space-y-3">{children}</div>
    </section>
  );
}
