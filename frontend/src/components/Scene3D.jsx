import { useEffect, useRef } from "react";
import {
  AdditiveBlending, BufferAttribute, BufferGeometry, Color, EdgesGeometry, Fog, GridHelper, IcosahedronGeometry, LineBasicMaterial,
  LineSegments, Mesh, MeshBasicMaterial, PerspectiveCamera, Points, PointsMaterial, Scene, TorusGeometry, WebGLRenderer,
} from "three";

/** Fixed full-screen background: neon grid floor racing toward the camera, a rotating wireframe "shield core",
 *  orbit rings and drifting particles. Mouse parallax. Renders a single frame if the user prefers reduced motion. */
export default function Scene3D({ intensity = 1, landing = false }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    let renderer;
    try { renderer = new WebGLRenderer({ antialias: true, alpha: true }); } catch { return; } // no WebGL: CSS atmosphere still shows
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    el.appendChild(renderer.domElement);
    const scene = new Scene();
    scene.fog = new Fog(0x04050d, 8, 42);
    const cam = new PerspectiveCamera(60, 1, 0.1, 100);
    cam.position.set(0, 2.2, 9);

    const grid = new GridHelper(120, 80, 0xff2bd6, 0x00f0ff);
    grid.position.y = -3.2;
    grid.material.transparent = true; grid.material.opacity = 0.45;
    const grid2 = grid.clone(); grid2.position.y = 9; grid2.material = grid.material.clone(); grid2.material.opacity = 0.12;
    scene.add(grid, grid2);

    const core = new Mesh(new IcosahedronGeometry(2.1, 1), new MeshBasicMaterial({ color: 0x021a2b, transparent: true, opacity: 0.55 }));
    const wire = new LineSegments(new EdgesGeometry(new IcosahedronGeometry(2.15, 1)), new LineBasicMaterial({ color: 0x00f0ff }));
    const inner = new LineSegments(new EdgesGeometry(new IcosahedronGeometry(1.1, 0)), new LineBasicMaterial({ color: 0xff2bd6 }));
    const ringA = new Mesh(new TorusGeometry(3.3, 0.012, 8, 160), new MeshBasicMaterial({ color: 0x8a5cff }));
    const ringB = new Mesh(new TorusGeometry(3.9, 0.012, 8, 160), new MeshBasicMaterial({ color: 0x00f0ff }));
    ringA.rotation.x = 1.2; ringB.rotation.y = 1.1;
    const hero = [core, wire, inner, ringA, ringB];
    const HX = landing ? 0 : 4.2, HY = landing ? 3.4 : 1.2, HZ = landing ? -7 : -4;
    hero.forEach((o) => { o.position.set(HX, HY, HZ); scene.add(o); });

    const N = 700, pos = new Float32Array(N * 3), col = new Float32Array(N * 3), c = new Color();
    for (let i = 0; i < N; i++) {
      pos.set([(Math.random() - 0.5) * 60, Math.random() * 18 - 3, (Math.random() - 0.5) * 50], i * 3);
      c.set(Math.random() > 0.5 ? 0x00f0ff : 0xff2bd6); col.set([c.r, c.g, c.b], i * 3);
    }
    const g = new BufferGeometry();
    g.setAttribute("position", new BufferAttribute(pos, 3)); g.setAttribute("color", new BufferAttribute(col, 3));
    const dust = new Points(g, new PointsMaterial({ size: 0.07, vertexColors: true, transparent: true, opacity: 0.8, blending: AdditiveBlending, depthWrite: false }));
    scene.add(dust);

    const mouse = { x: 0, y: 0 };
    const onMove = (e) => { mouse.x = (e.clientX / innerWidth - 0.5) * 2; mouse.y = (e.clientY / innerHeight - 0.5) * 2; };
    const resize = () => { const w = el.clientWidth, h = el.clientHeight; renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix();
      hero.forEach((o) => o.position.x = w < 800 ? 0 : HX); };
    addEventListener("mousemove", onMove); addEventListener("resize", resize); resize();

    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf, t0 = performance.now();
    const frame = (now) => {
      const t = (now - t0) / 1000;
      grid.position.z = (t * 2.2 * intensity) % (120 / 80);       // one cell loop => seamless forward motion
      wire.rotation.y = core.rotation.y = t * 0.25; wire.rotation.x = core.rotation.x = Math.sin(t * 0.3) * 0.3;
      inner.rotation.y = -t * 0.6; inner.rotation.x = t * 0.4;
      ringA.rotation.z = t * 0.3; ringB.rotation.z = -t * 0.22;
      dust.rotation.y = t * 0.012;
      cam.position.x += (mouse.x * 1.4 - cam.position.x) * 0.04; cam.position.y += (2.2 - mouse.y * 0.8 - cam.position.y) * 0.04;
      cam.lookAt(0, 0.6, -4);
      renderer.render(scene, cam);
      if (!still) raf = requestAnimationFrame(frame);
    };
    frame(performance.now());
    if (!still) raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf); removeEventListener("mousemove", onMove); removeEventListener("resize", resize);
      scene.traverse((o) => { o.geometry?.dispose(); (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m?.dispose()); });
      renderer.dispose(); renderer.domElement.remove();
    };
  }, [intensity, landing]);

  return <div className="scene" ref={ref} aria-hidden="true" />;
}
