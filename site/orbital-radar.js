(() => {
  const canvas = document.querySelector('.radar-art canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const turn = 2 * Math.PI;
  const orbits = [
    { angle: -.65, radius: 105, height: 32, speed: 1.3, phase: .31, color: '#c6fc8a' },
    { angle: .33, radius: 98, height: 39, speed: 1.11, phase: 2.27, color: '#74e8d0' },
    { angle: 1.05, radius: 91, height: 46, speed: .92, phase: 4.22, color: '#a9d7f7' },
  ].map(orbit => ({ ...orbit, cos: Math.cos(orbit.angle), sin: Math.sin(orbit.angle) }));

  function position(orbit, phase, offset = 0) {
    const x = (orbit.radius + offset) * Math.cos(phase);
    const y = (orbit.height + offset) * Math.sin(phase);
    return { x: x * orbit.cos - y * orbit.sin, y: x * orbit.sin + y * orbit.cos };
  }

  const particles = orbits.flatMap((orbit, lane) =>
    Array.from({ length: 16 }, (_, index) => ({
      ...position(orbit, index * 2.39996 + lane, 6 + 13 * Math.sin(index * 3.19 + lane)),
      size: 1 + (index % 4) * .27, inside: false, revealed: -Infinity, color: orbit.color,
    }))
  );
  const rise = .085;
  const fade = 1.8;
  let time = 0;
  let previous;
  let frame;

  function dot(x, y, radius, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, turn);
    ctx.fill();
  }

  function draw() {
    const { clientWidth: width, clientHeight: height } = canvas;
    if (!width || !height) return;
    const density = Math.min(devicePixelRatio || 1, 2);
    const pixelWidth = Math.round(width * density);
    const pixelHeight = Math.round(height * density);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    ctx.setTransform(density, 0, 0, density, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.translate(width / 2, height / 2);
    const scale = Math.min(width / 258, height / 226);
    ctx.scale(scale, scale);

    const atoms = orbits.map(orbit => {
      ctx.strokeStyle = '#39574e';
      ctx.beginPath();
      ctx.ellipse(0, 0, orbit.radius, orbit.height, orbit.angle, 0, turn);
      ctx.stroke();
      const phase = orbit.phase + time * orbit.speed;
      for (let step = 19; step > 0; step--) {
        const trail = position(orbit, phase - step * .05);
        ctx.globalAlpha = ((20 - step) / 20) ** 2 * .65;
        dot(trail.x, trail.y, 1.9, orbit.color);
      }
      ctx.globalAlpha = 1;
      return { ...position(orbit, phase), color: orbit.color };
    });

    if (!reducedMotion.matches) {
      for (const particle of particles) {
        const near = atoms.some(atom => (atom.x - particle.x) ** 2 + (atom.y - particle.y) ** 2 < 17 ** 2);
        if (near && !particle.inside && time - particle.revealed >= rise + fade) particle.revealed = time;
        particle.inside = near;
        const age = time - particle.revealed;
        if (age >= rise + fade) continue;
        const brightness = age < rise ? 1 - (1 - age / rise) ** 3 : (1 - (age - rise) / fade) ** 2;
        ctx.globalAlpha = brightness;
        ctx.shadowColor = particle.color;
        ctx.shadowBlur = 11 * brightness;
        dot(particle.x, particle.y, particle.size + brightness, particle.color);
      }
    }

    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;
    const glow = ctx.createRadialGradient(0, 0, 2, 0, 0, 37);
    glow.addColorStop(0, '#d3ffa5');
    glow.addColorStop(.22, '#a1e89785');
    glow.addColorStop(1, '#a1e89700');
    dot(0, 0, 37, glow);
    dot(0, 0, 4.5, '#e3ffc8');
    for (const atom of atoms) {
      ctx.shadowColor = atom.color;
      ctx.shadowBlur = 14;
      dot(atom.x, atom.y, 3.4, atom.color);
    }
    ctx.restore();
  }

  function animate(now) {
    time += Math.min((now - (previous ?? now)) / 1000, .05);
    previous = now;
    draw();
    frame = requestAnimationFrame(animate);
  }

  function syncMotion() {
    cancelAnimationFrame(frame);
    previous = undefined;
    draw();
    if (!reducedMotion.matches && !document.hidden) frame = requestAnimationFrame(animate);
  }

  reducedMotion.addEventListener('change', syncMotion);
  document.addEventListener('visibilitychange', syncMotion);
  new ResizeObserver(draw).observe(canvas);
  syncMotion();
})();
