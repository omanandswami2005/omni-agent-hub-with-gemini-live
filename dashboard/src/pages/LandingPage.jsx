import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router';
import {
  Smartphone, Monitor, Globe, Box, Settings, Share2,
  Play, ArrowRight, Layers, BrainCircuit, ChevronRight,
  Github, Youtube, FileText, ExternalLink, Menu, X
} from 'lucide-react';

const LandingPage = () => {
  const [activeFeature, setActiveFeature] = useState(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const canvasRef = useRef(null);

  /* ── Animated background: connected dots & lines ── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animId;
    const dpr = window.devicePixelRatio || 1;

    const nodes = [];
    const NODE_COUNT = 50;
    const CONNECT_DIST = 160;

    const resize = () => {
      canvas.width = canvas.offsetWidth * dpr;
      canvas.height = canvas.offsetHeight * dpr;
      ctx.scale(dpr, dpr);
    };

    const init = () => {
      resize();
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      nodes.length = 0;
      for (let i = 0; i < NODE_COUNT; i++) {
        nodes.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.4,
          vy: (Math.random() - 0.5) * 0.4,
          r: Math.random() * 2 + 1,
        });
      }
    };

    const draw = () => {
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      ctx.clearRect(0, 0, w, h);

      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        a.x += a.vx;
        a.y += a.vy;
        if (a.x < 0 || a.x > w) a.vx *= -1;
        if (a.y < 0 || a.y > h) a.vy *= -1;

        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < CONNECT_DIST) {
            const opacity = 1 - dist / CONNECT_DIST;
            ctx.strokeStyle = `rgba(168, 85, 247, ${opacity * 0.25})`;
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }

        ctx.fillStyle = 'rgba(168, 85, 247, 0.6)';
        ctx.beginPath();
        ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
        ctx.fill();
      }

      animId = requestAnimationFrame(draw);
    };

    init();
    draw();
    window.addEventListener('resize', init);
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', init);
    };
  }, []);

  const features = [
    {
      title: "One Voice, Every Device",
      description: "Speak from your phone, see results on your dashboard, trigger actions on your desktop.",
      icon: <Layers className="w-6 h-6" />,
      color: "text-blue-500",
      bgColor: "bg-blue-500/10"
    },
    {
      title: "MCP Plugin Store",
      description: "Install new agent capabilities in one click, like an app store for AI skills.",
      icon: <Box className="w-6 h-6" />,
      color: "text-purple-500",
      bgColor: "bg-purple-500/10"
    },
    {
      title: "GenUI & Live Render",
      description: "Agent renders live charts, tables, code blocks, and cards on your dashboard.",
      icon: <Monitor className="w-6 h-6" />,
      color: "text-green-500",
      bgColor: "bg-green-500/10"
    },
    {
      title: "Agent Personas",
      description: "Switch between specialized AI personalities (analyst, coder, researcher).",
      icon: <BrainCircuit className="w-6 h-6" />,
      color: "text-amber-500",
      bgColor: "bg-amber-500/10"
    },
    {
      title: "Browser Control",
      description: "Tell your agent to scrape a website, fill a form, or extract data — all by voice.",
      icon: <Globe className="w-6 h-6" />,
      color: "text-rose-500",
      bgColor: "bg-rose-500/10"
    },
    {
      title: "Cross-Client Actions",
      description: "Save a task on your phone and it appears on your desktop instantly.",
      icon: <Share2 className="w-6 h-6" />,
      color: "text-cyan-500",
      bgColor: "bg-cyan-500/10"
    }
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-zinc-50 font-sans selection:bg-purple-500/30">
      {/* Animated Background Canvas */}
      <canvas ref={canvasRef} className="fixed inset-0 w-full h-full pointer-events-none z-0" />

      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/10 bg-black/40 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center shadow-lg shadow-purple-500/25">
              <BrainCircuit className="w-5 h-5 text-white" />
            </div>
            {/* Voice wave bars as logo */}
            <div className="flex items-center gap-[3px]">
              {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
                <div
                  key={i}
                  className="w-[3px] rounded-full bg-gradient-to-t from-purple-500 to-blue-400"
                  style={{
                    animation: `voice-wave 1.2s ease-in-out ${i * 0.1}s infinite`,
                    height: '6px',
                  }}
                />
              ))}
            </div>
          </div>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-5">
            <a href="#features" className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">Features</a>
            <a href="#how-it-works" className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">How it Works</a>
            <a href="https://github.com/omanandswami2005/omni-agent-hub-with-gemini-live" target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-white transition-colors" title="GitHub">
              <Github className="w-5 h-5" />
            </a>
            <a href="https://www.youtube.com/@omanandswami" target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-white transition-colors" title="YouTube">
              <Youtube className="w-5 h-5" />
            </a>
            <a href="https://omanandswami2005.github.io/omni-agent-hub-with-gemini-live/" target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-white transition-colors" title="Documentation">
              <FileText className="w-5 h-5" />
            </a>
            <Link to="/login" className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">Sign In</Link>
            <Link to="/register" className="text-sm font-medium bg-white text-black px-4 py-2 rounded-full hover:bg-zinc-200 transition-colors">
              Get Started
            </Link>
          </div>

          {/* Hamburger button - mobile only */}
          <button
            className="md:hidden text-zinc-400 hover:text-white transition-colors"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile dropdown menu */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-white/10 bg-black/95 backdrop-blur-xl px-6 py-6 flex flex-col gap-4">
            <a href="#features" onClick={() => setMobileMenuOpen(false)} className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">Features</a>
            <a href="#how-it-works" onClick={() => setMobileMenuOpen(false)} className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">How it Works</a>
            <a href="https://github.com/omanandswami2005/omni-agent-hub-with-gemini-live" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm font-medium text-zinc-400 hover:text-white transition-colors">
              <Github className="w-4 h-4" /> GitHub
            </a>
            <a href="https://www.youtube.com/@omanandswami" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm font-medium text-zinc-400 hover:text-white transition-colors">
              <Youtube className="w-4 h-4" /> YouTube
            </a>
            <a href="https://omanandswami2005.github.io/omni-agent-hub-with-gemini-live/" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm font-medium text-zinc-400 hover:text-white transition-colors">
              <FileText className="w-4 h-4" /> Docs
            </a>
            <hr className="border-white/10" />
            <Link to="/login" onClick={() => setMobileMenuOpen(false)} className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">Sign In</Link>
            <Link to="/register" onClick={() => setMobileMenuOpen(false)} className="text-sm font-medium bg-white text-black px-4 py-2 rounded-full hover:bg-zinc-200 transition-colors text-center">
              Get Started
            </Link>
          </div>
        )}
      </nav>

      {/* Hero Section */}
      <section className="relative pt-24 pb-20 overflow-hidden">
        {/* Gradient overlays */}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(120,0,255,0.15),transparent_50%)]"></div>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(0,100,255,0.12),transparent_50%)]"></div>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_bottom_center,rgba(168,85,247,0.08),transparent_60%)]"></div>

        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="flex flex-col items-center text-center max-w-4xl mx-auto mt-8">

            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-sm font-medium text-purple-300 mb-6" style={{ animation: 'fade-in-down 0.8s ease-out both' }}>
              <SparklesIcon className="w-4 h-4" />
              <span>Gemini Live Agent Challenge</span>
            </div>

            {/* Heading with stagger animations */}
            <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6 leading-tight">
              <span className="block text-transparent bg-clip-text bg-gradient-to-r from-white to-white/70" style={{ animation: 'fade-in-up 0.9s ease-out 0.1s both' }}>
                Speak anywhere.
              </span>
              <span className="block text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-blue-400" style={{ animation: 'fade-in-up 0.9s ease-out 0.3s both' }}>
                Act everywhere.
              </span>
            </h1>

            <p className="text-lg md:text-xl text-zinc-400 mb-8 max-w-2xl leading-relaxed" style={{ animation: 'fade-in-up 0.9s ease-out 0.5s both' }}>
              One AI brain. Every device. Infinite capabilities. Connect your entire digital life with a single, intelligent agent that spans across web, mobile, desktop, and smart glasses.
            </p>

            {/* OMNI colorful voice wave text */}
            <div className="flex items-center justify-center gap-1 md:gap-2 mb-8" style={{ animation: 'fade-in-up 0.9s ease-out 0.6s both' }}>
              {'OMNI'.split('').map((letter, i) => (
                <span
                  key={i}
                  className="text-5xl md:text-7xl font-black inline-block"
                  style={{
                    animation: `omni-color-wave 3s ease-in-out ${i * 0.4}s infinite, omni-bounce 2s ease-in-out ${i * 0.2}s infinite`,
                    background: 'linear-gradient(90deg, #a855f7, #3b82f6, #06b6d4, #22c55e, #eab308, #a855f7)',
                    backgroundSize: '300% 100%',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    backgroundClip: 'text',
                  }}
                >
                  {letter}
                </span>
              ))}
            </div>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row items-center gap-4 w-full sm:w-auto mb-8" style={{ animation: 'fade-in-up 0.9s ease-out 0.7s both' }}>
              <Link to="/register" className="w-full sm:w-auto px-8 py-4 rounded-full bg-white text-black font-semibold text-lg hover:bg-zinc-200 hover:scale-105 transition-all duration-300 flex items-center justify-center gap-2 group">
                Start Building Free
                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Link>
              <a href="#demo" className="w-full sm:w-auto px-8 py-4 rounded-full bg-white/5 text-white border border-white/10 font-semibold text-lg hover:bg-white/10 transition-all duration-300 flex items-center justify-center gap-2 backdrop-blur-sm">
                <Play className="w-5 h-5" fill="currentColor" />
                Watch Demo
              </a>
            </div>

            {/* Powered by Gemini Live badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 backdrop-blur-md" style={{ animation: 'fade-in-up 0.9s ease-out 0.9s both' }}>
              <GeminiIcon className="w-5 h-5 text-blue-400" />
              <span className="text-xs font-medium text-zinc-400">Powered by</span>
              <span className="text-sm font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">Gemini Live</span>
            </div>

            {/* Quick links row */}
            <div className="flex items-center gap-6 mt-6" style={{ animation: 'fade-in-up 0.9s ease-out 1s both' }}>
              <a href="https://github.com/omanandswami2005/omni-agent-hub-with-gemini-live" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-zinc-500 hover:text-white transition-colors group">
                <Github className="w-4 h-4" />
                GitHub
                <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
              <a href="https://www.youtube.com/@omanandswami" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-zinc-500 hover:text-white transition-colors group">
                <Youtube className="w-4 h-4" />
                YouTube
                <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
              <a href="https://omanandswami2005.github.io/omni-agent-hub-with-gemini-live/" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-zinc-500 hover:text-white transition-colors group">
                <FileText className="w-4 h-4" />
                Docs
                <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Cross-Device Visualization */}
      <section className="py-20 border-y border-white/5 relative" id="how-it-works">
        <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>
        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold mb-4">Every AI assistant is an island. <span className="text-purple-400">Not anymore.</span></h2>
            <p className="text-zinc-400 max-w-2xl mx-auto">Omni connects one AI brain to every device you own. Switch devices mid-thought and pick up exactly where you left off.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 relative">
            {/* Connection Lines (Desktop) */}
            <div className="hidden md:block absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-purple-500/50 to-transparent -translate-y-1/2 z-0"></div>

            {[
              { icon: <Monitor className="w-10 h-10" />, name: "Web Dashboard", desc: "GenUI & Analytics" },
              { icon: <Smartphone className="w-10 h-10" />, name: "Mobile PWA", desc: "Vision & Voice" },
              { icon: <Box className="w-10 h-10" />, name: "Desktop App", desc: "Local Execution" },
              { icon: <Settings className="w-10 h-10" />, name: "Protocol Ready", desc: "WebSockets Based" }
            ].map((device, i) => (
              <div key={i} className="relative z-10 flex flex-col items-center p-8 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-xl hover:border-purple-500/50 transition-all duration-500 group hover:bg-white/[0.06] hover:shadow-[0_8px_32px_rgba(168,85,247,0.15)]" style={{ animation: `fade-in-up 0.8s ease-out ${0.2 + i * 0.15}s both` }}>
                <div className="relative w-20 h-20 rounded-full bg-black/50 border border-white/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-500 text-zinc-300 group-hover:text-white">
                  {/* Pulse ring on hover */}
                  <div className="absolute inset-0 rounded-full border border-purple-500/0 group-hover:border-purple-500/30 group-hover:animate-[pulse-ring_1.5s_ease-out_infinite]"></div>
                  {device.icon}
                </div>
                <h3 className="text-lg font-semibold mb-2">{device.name}</h3>
                <p className="text-sm text-zinc-500 text-center">{device.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Feature Grid / Carousel */}
      <section id="features" className="py-24 relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col md:flex-row gap-12 items-center">
            {/* Feature List */}
            <div className="w-full md:w-1/2 space-y-2">
              <h2 className="text-3xl md:text-4xl font-bold mb-8">Infinite capabilities.<br />Zero friction.</h2>

              {features.map((feature, idx) => (
                <div
                  key={idx}
                  className={`p-6 rounded-2xl cursor-pointer transition-all duration-300 border backdrop-blur-sm ${activeFeature === idx
                    ? 'bg-white/[0.06] border-white/15 shadow-lg shadow-purple-500/5'
                    : 'border-transparent hover:bg-white/[0.03]'
                    }`}
                  onClick={() => setActiveFeature(idx)}
                >
                  <div className="flex items-start gap-4">
                    <div className={`p-3 rounded-xl ${feature.bgColor} ${feature.color}`}>
                      {feature.icon}
                    </div>
                    <div>
                      <h3 className={`text-xl font-semibold mb-2 ${activeFeature === idx ? 'text-white' : 'text-zinc-300'}`}>
                        {feature.title}
                      </h3>
                      <p className={`text-sm leading-relaxed ${activeFeature === idx ? 'text-zinc-400' : 'text-zinc-500'}`}>
                        {feature.description}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Feature Visual — glass card */}
            <div className="w-full md:w-1/2">
              <div className="aspect-square rounded-3xl bg-white/[0.03] border border-white/10 backdrop-blur-xl p-8 flex items-center justify-center relative overflow-hidden group shadow-[0_8px_40px_rgba(168,85,247,0.08)]">
                {/* Dynamic Background */}
                <div className={`absolute inset-0 opacity-20 transition-colors duration-1000 ${features[activeFeature].bgColor.replace('/10', '/30')}`}></div>

                {/* Visual Content */}
                <div className="relative z-10 w-full h-full flex flex-col items-center justify-center text-center" key={activeFeature} style={{ animation: 'fade-in-up 0.5s ease-out both' }}>
                  <div className={`w-32 h-32 rounded-full mb-8 flex items-center justify-center ${features[activeFeature].bgColor} ${features[activeFeature].color}`} style={{ animation: 'float 3s ease-in-out infinite' }}>
                    {React.cloneElement(features[activeFeature].icon, { className: "w-16 h-16" })}
                  </div>
                  <h3 className="text-2xl font-bold mb-4">{features[activeFeature].title}</h3>
                  <div className="w-full max-w-sm h-32 bg-black/30 backdrop-blur-md rounded-xl border border-white/10 p-4 flex items-center justify-center shadow-inner">
                    <div className="flex gap-2 items-center text-zinc-500">
                      <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                      Interactive Demo Preview
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Demo Moments Section */}
      <section id="demo" className="py-24 relative border-t border-white/5">
        <div className="absolute inset-0 bg-zinc-950/80"></div>
        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Experience the Magic</h2>
            <p className="text-zinc-400 max-w-2xl mx-auto">See how Omni seamlessly blends voice, visual UI, and actions across platforms.</p>
            {/* Voice wave divider */}
            <div className="flex items-center justify-center gap-1 mt-6">
              {[0, 1, 2, 3, 4, 3, 2, 1, 0].map((_, i) => (
                <div key={i} className="w-0.5 rounded-full bg-gradient-to-t from-purple-600/40 to-blue-500/40" style={{ animation: `voice-wave 1.5s ease-in-out ${i * 0.12}s infinite`, height: '6px' }} />
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                title: "Voice + GenUI",
                trigger: "Show me Tesla's stock...",
                action: "Agent speaks the answer while a real-time chart renders instantly on your dashboard.",
                icon: <Monitor className="w-6 h-6 text-blue-400" />
              },
              {
                title: "Persona Switch",
                trigger: "Switch to Atlas...",
                action: "Voice changes instantly. Ask for code, it renders a code block, then executes it in a secure sandbox.",
                icon: <BrainCircuit className="w-6 h-6 text-purple-400" />
              },
              {
                title: "Cross-Client Sync",
                trigger: "Analyze this image...",
                action: "Point your phone camera. Agent describes it. Say 'Save to dashboard', switch to desktop—it's there.",
                icon: <Smartphone className="w-6 h-6 text-green-400" />
              }
            ].map((demo, idx) => (
              <div key={idx} className="bg-white/[0.03] border border-white/10 rounded-2xl p-8 backdrop-blur-xl hover:-translate-y-2 transition-all duration-500 hover:shadow-[0_12px_40px_rgba(168,85,247,0.12)] hover:border-purple-500/30" style={{ animation: `fade-in-up 0.8s ease-out ${0.2 + idx * 0.15}s both` }}>
                <div className="w-12 h-12 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center mb-6 backdrop-blur-sm">
                  {demo.icon}
                </div>
                <h3 className="text-xl font-bold mb-4">{demo.title}</h3>
                <div className="mb-4 p-4 rounded-xl bg-black/30 border border-white/5 font-mono text-sm text-zinc-300 backdrop-blur-md">
                  <span className="text-purple-400">You:</span> "{demo.trigger}"
                </div>
                <p className="text-zinc-400 text-sm leading-relaxed">
                  {demo.action}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-32 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-purple-900/10 to-purple-900/20"></div>
        <div className="max-w-4xl mx-auto px-6 relative z-10 text-center">
          <h2 className="text-4xl md:text-5xl font-bold mb-8">Ready to unify your digital life?</h2>
          <p className="text-xl text-zinc-400 mb-8">
            Join thousands of users building the future of human-computer interaction with Omni.
          </p>
          {/* Voice wave */}
          <div className="flex items-center justify-center gap-1.5 mb-10">
            {[0, 1, 2, 3, 4, 5, 6, 4, 3, 2, 1, 0].map((_, i) => (
              <div key={i} className="w-1 rounded-full bg-gradient-to-t from-purple-500/60 to-blue-400/60" style={{ animation: `voice-wave 1.4s ease-in-out ${i * 0.08}s infinite`, height: '6px' }} />
            ))}
          </div>
          <Link to="/register" className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-full bg-white text-black font-bold text-lg hover:scale-105 transition-transform duration-300">
            Get Started for Free
            <ChevronRight className="w-5 h-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 py-12 bg-black/80 backdrop-blur-sm relative z-10">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <BrainCircuit className="w-6 h-6 text-purple-500" />
            <span className="text-lg font-bold tracking-tight">OMNI</span>
            <span className="text-xs text-zinc-600 ml-2">|</span>
            <div className="flex items-center gap-1.5 ml-1">
              <GeminiIcon className="w-4 h-4 text-blue-400" />
              <span className="text-xs text-zinc-500">Powered by <span className="text-zinc-400 font-medium">Gemini Live</span></span>
            </div>
          </div>
          <p className="text-sm text-zinc-500">
            Built for the Gemini Live Agent Challenge.
          </p>
          <div className="flex items-center gap-5">
            <a href="https://github.com/omanandswami2005/omni-agent-hub-with-gemini-live" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors">
              <Github className="w-4 h-4" />
              GitHub
            </a>
            <a href="https://omanandswami2005.github.io/omni-agent-hub-with-gemini-live/" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors">
              <FileText className="w-4 h-4" />
              Docs
            </a>
            <a href="https://www.youtube.com/@omanandswami" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors">
              <Youtube className="w-4 h-4" />
              YouTube
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};

// Gemini icon (simplified star/sparkle logo)
const GeminiIcon = (props) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" {...props}>
    <path d="M12 2C12 2 14.5 8.5 12 12C9.5 8.5 12 2 12 2Z" fill="currentColor" opacity="0.7" />
    <path d="M12 22C12 22 14.5 15.5 12 12C9.5 15.5 12 22 12 22Z" fill="currentColor" opacity="0.7" />
    <path d="M2 12C2 12 8.5 9.5 12 12C8.5 14.5 2 12 2 12Z" fill="currentColor" opacity="0.7" />
    <path d="M22 12C22 12 15.5 9.5 12 12C15.5 14.5 22 12 22 12Z" fill="currentColor" opacity="0.7" />
    <circle cx="12" cy="12" r="2" fill="currentColor" />
  </svg>
);

// Simple Sparkles icon helper since we don't have lucide-react sparkles imported explicitly
const SparklesIcon = (props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
    <path d="M5 3v4" />
    <path d="M19 17v4" />
    <path d="M3 5h4" />
    <path d="M17 19h4" />
  </svg>
);

export default LandingPage;
