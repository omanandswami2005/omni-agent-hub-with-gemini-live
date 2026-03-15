import React, { useState } from 'react';
import { Link } from 'react-router';
import {
  Smartphone, Monitor, Globe, Box, Settings, Cpu, Share2,
  Play, ArrowRight, Layers, BrainCircuit, ChevronRight
} from 'lucide-react';

const LandingPage = () => {
  const [activeFeature, setActiveFeature] = useState(0);

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
      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/10 bg-black/50 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center">
              <Cpu className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold tracking-tight">OMNI</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#features" className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">Features</a>
            <a href="#how-it-works" className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">How it Works</a>
            <Link to="/login" className="text-sm font-medium text-zinc-400 hover:text-white transition-colors">Sign In</Link>
            <Link to="/register" className="text-sm font-medium bg-white text-black px-4 py-2 rounded-full hover:bg-zinc-200 transition-colors">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(120,0,255,0.1),transparent_50%)]"></div>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(0,100,255,0.1),transparent_50%)]"></div>

        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="flex flex-col items-center text-center max-w-4xl mx-auto mt-16">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-sm font-medium text-purple-300 mb-8 animate-[fade-in_1s_ease-out]">
              <SparklesIcon className="w-4 h-4" />
              <span>Gemini Live Agent Challenge</span>
            </div>

            <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-8 leading-tight">
              <span className="block text-transparent bg-clip-text bg-gradient-to-r from-white to-white/70">
                Speak anywhere.
              </span>
              <span className="block text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-blue-400">
                Act everywhere.
              </span>
            </h1>

            <p className="text-lg md:text-xl text-zinc-400 mb-12 max-w-2xl leading-relaxed">
              One AI brain. Every device. Infinite capabilities. Connect your entire digital life with a single, intelligent agent that spans across web, mobile, desktop, and smart glasses.
            </p>

            <div className="flex flex-col sm:flex-row items-center gap-4 w-full sm:w-auto">
              <Link to="/register" className="w-full sm:w-auto px-8 py-4 rounded-full bg-white text-black font-semibold text-lg hover:bg-zinc-200 hover:scale-105 transition-all duration-300 flex items-center justify-center gap-2 group">
                Start Building Free
                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Link>
              <a href="#demo" className="w-full sm:w-auto px-8 py-4 rounded-full bg-white/5 text-white border border-white/10 font-semibold text-lg hover:bg-white/10 transition-all duration-300 flex items-center justify-center gap-2">
                <Play className="w-5 h-5" fill="currentColor" />
                Watch Demo
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Cross-Device Visualization */}
      <section className="py-20 border-y border-white/5 bg-black/50" id="how-it-works">
        <div className="max-w-7xl mx-auto px-6">
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
              { icon: <Settings className="w-10 h-10" />, name: "Smart Glasses", desc: "AR Overlay" }
            ].map((device, i) => (
              <div key={i} className="relative z-10 flex flex-col items-center p-8 rounded-2xl bg-zinc-900/50 border border-white/10 backdrop-blur-sm hover:border-purple-500/50 transition-colors group">
                <div className="w-20 h-20 rounded-full bg-black border border-white/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-500 group-hover:shadow-[0_0_30px_rgba(168,85,247,0.3)] text-zinc-300 group-hover:text-white">
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
              <h2 className="text-3xl md:text-4xl font-bold mb-8">Infinite capabilities.<br/>Zero friction.</h2>

              {features.map((feature, idx) => (
                <div
                  key={idx}
                  className={`p-6 rounded-2xl cursor-pointer transition-all duration-300 border ${
                    activeFeature === idx
                      ? 'bg-white/5 border-white/10 shadow-lg'
                      : 'border-transparent hover:bg-white/[0.02]'
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

            {/* Feature Visual */}
            <div className="w-full md:w-1/2">
              <div className="aspect-square rounded-3xl bg-zinc-900/80 border border-white/10 p-8 flex items-center justify-center relative overflow-hidden group">
                {/* Dynamic Background */}
                <div className={`absolute inset-0 opacity-20 transition-colors duration-1000 ${features[activeFeature].bgColor.replace('/10', '/30')}`}></div>

                {/* Visual Content based on active feature */}
                <div className="relative z-10 w-full h-full flex flex-col items-center justify-center text-center animate-[fade-in_0.5s_ease-out]" key={activeFeature}>
                  <div className={`w-32 h-32 rounded-full mb-8 flex items-center justify-center ${features[activeFeature].bgColor} ${features[activeFeature].color}`}>
                    {React.cloneElement(features[activeFeature].icon, { className: "w-16 h-16" })}
                  </div>
                  <h3 className="text-2xl font-bold mb-4">{features[activeFeature].title}</h3>
                  <div className="w-full max-w-sm h-32 bg-black/50 rounded-xl border border-white/10 p-4 flex items-center justify-center shadow-inner">
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
      <section id="demo" className="py-24 bg-zinc-950 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Experience the Magic</h2>
            <p className="text-zinc-400 max-w-2xl mx-auto">See how Omni seamlessly blends voice, visual UI, and actions across platforms.</p>
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
              <div key={idx} className="bg-zinc-900 border border-white/10 rounded-2xl p-8 hover:-translate-y-2 transition-transform duration-300">
                <div className="w-12 h-12 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center mb-6">
                  {demo.icon}
                </div>
                <h3 className="text-xl font-bold mb-4">{demo.title}</h3>
                <div className="mb-4 p-4 rounded-xl bg-black/50 border border-white/5 font-mono text-sm text-zinc-300">
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
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-purple-900/20"></div>
        <div className="max-w-4xl mx-auto px-6 relative z-10 text-center">
          <h2 className="text-4xl md:text-5xl font-bold mb-8">Ready to unify your digital life?</h2>
          <p className="text-xl text-zinc-400 mb-12">
            Join thousands of users building the future of human-computer interaction with Omni.
          </p>
          <Link to="/register" className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-full bg-white text-black font-bold text-lg hover:scale-105 transition-transform duration-300">
            Get Started for Free
            <ChevronRight className="w-5 h-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 py-12 bg-black">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <Cpu className="w-6 h-6 text-purple-500" />
            <span className="text-lg font-bold tracking-tight">OMNI</span>
          </div>
          <p className="text-sm text-zinc-500">
            Built for the Gemini Live Agent Challenge.
          </p>
          <div className="flex gap-4 text-sm text-zinc-400">
            <a href="#" className="hover:text-white transition-colors">GitHub</a>
            <a href="#" className="hover:text-white transition-colors">Documentation</a>
            <a href="#" className="hover:text-white transition-colors">Twitter</a>
          </div>
        </div>
      </footer>
    </div>
  );
};

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
    <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
    <path d="M5 3v4"/>
    <path d="M19 17v4"/>
    <path d="M3 5h4"/>
    <path d="M17 19h4"/>
  </svg>
);

export default LandingPage;
