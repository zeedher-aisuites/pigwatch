const foundations = [
  "Simulation-first source boundaries",
  "Explicit data provenance",
  "Shared validation contracts",
  "Automated quality checks",
];

export function App() {
  return (
    <main className="shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">PigWatch · M0</p>
        <h1 id="page-title">Engineering foundation ready</h1>
        <p className="lede">
          The product data path is intentionally offline while telemetry contracts are designed for
          M1.
        </p>
        <ul>
          {foundations.map((foundation) => (
            <li key={foundation}>{foundation}</li>
          ))}
        </ul>
        <aside>
          PigWatch supports anomaly awareness and professional decision-making. It does not
          independently diagnose veterinary disease.
        </aside>
      </section>
    </main>
  );
}
