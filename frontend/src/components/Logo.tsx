import React from 'react';

interface LogoProps {
  className?: string;
  size?: number | string;
  showText?: boolean;
}

const Logo: React.FC<LogoProps> = ({ className = '', size = 48, showText = false }) => {
  const finalSize = Number(size) || 48;
  const height = finalSize * (250 / 180);

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <svg 
        width={finalSize} 
        height={height} 
        viewBox="10 0 180 250" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
            {/* Exactly the same gradients from index.html */}
            <radialGradient id="gf" cx="50%" cy="30%" r="70%">
                <stop offset="0%" stopColor="#322a40" />
                <stop offset="40%" stopColor="#1f1a29" />
                <stop offset="75%" stopColor="#110e17" />
                <stop offset="100%" stopColor="#050407" />
            </radialGradient>
            
            <radialGradient id="g-form" cx="50%" cy="40%" r="70%" fx="50%" fy="30%">
                <stop offset="0%" stopColor="rgba(180, 160, 220, 0.08)" />
                <stop offset="40%" stopColor="rgba(180, 160, 220, 0.02)" />
                <stop offset="100%" stopColor="rgba(180, 160, 220, 0)" />
            </radialGradient>

            <linearGradient id="g-rim" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(200, 190, 240, 0.22)" />
                <stop offset="15%" stopColor="rgba(200, 190, 240, 0.04)" />
                <stop offset="50%" stopColor="rgba(200, 190, 240, 0)" />
                <stop offset="85%" stopColor="rgba(200, 190, 240, 0.04)" />
                <stop offset="100%" stopColor="rgba(200, 190, 240, 0.22)" />
            </linearGradient>

            <linearGradient id="g-eye" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#020103" />
                <stop offset="100%" stopColor="#161221" />
            </linearGradient>

            <radialGradient id="g-nose" cx="50%" cy="45%" r="40%" fx="50%" fy="35%">
                <stop offset="0%" stopColor="rgba(200, 190, 240, 0.07)" />
                <stop offset="25%" stopColor="rgba(200, 190, 240, 0.03)" />
                <stop offset="100%" stopColor="rgba(200, 190, 240, 0)" />
            </radialGradient>

            <radialGradient id="g-mouth" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#000000" />
                <stop offset="80%" stopColor="#0a080d" />
                <stop offset="100%" stopColor="#15121b" />
            </radialGradient>
        </defs>

        <path d="M100 10 C72 10,47 30,35 60 C25 90,25 115,35 140 C45 165,68 180,82 185 C92 188,108 188,118 185 C132 180,155 165,165 140 C175 115,175 90,165 60 C155 30,128 10,100 10Z" fill="url(#gf)" />
        <path d="M100 10 C72 10,47 30,35 60 C25 90,25 115,35 140 C45 165,68 180,82 185 C92 188,108 188,118 185 C132 180,155 165,165 140 C175 115,175 90,165 60 C155 30,128 10,100 10Z" fill="url(#g-form)" />
        <ellipse cx="100" cy="95" rx="8" ry="40" fill="url(#g-nose)" />
        <path d="M100 10 C72 10,47 30,35 60 C25 90,25 115,35 140 C45 165,68 180,82 185 C92 188,108 188,118 185 C132 180,155 165,165 140 C175 115,175 90,165 60 C155 30,128 10,100 10Z" stroke="url(#g-rim)" strokeWidth="2" fill="none" />
        <path d="M100 13 C75 13,49 32,39 61 C29 88,29 113,39 137 C49 161,71 176,86 181 C94 184,106 184,114 181 C129 176,151 161,161 137 C171 113,171 88,161 61 C151 32,125 13,100 13Z" stroke="rgba(190, 180, 220, 0.08)" strokeWidth="0.7" fill="none" />
        
        {/* Mouth */}
        <ellipse cx="100" cy="151.5" rx="12" ry="4" fill="rgba(0,0,0,0.25)" />
        <ellipse cx="100" cy="150" rx="10" ry="3" fill="url(#g-mouth)" />
        <path d="M91.5 151.2 Q100 153.2, 108.5 151.2" stroke="rgba(200, 190, 240, 0.12)" strokeWidth="0.8" fill="none" opacity="0.6" />
        <path d="M91 150 Q100 149, 109 150" stroke="rgba(0,0,0,0.5)" strokeWidth="1.2" fill="none" />

        {/* Eyes */}
        <path d="M52 82 C52 72, 62 68, 72 68 C82 68, 88 74, 88 82 C88 90, 80 94, 70 94 C60 94, 52 90, 52 82Z" fill="url(#g-eye)" stroke="rgba(200, 190, 230, 0.10)" strokeWidth="1.2" />
        <path d="M55 86 C60 92, 80 92, 85 86" fill="none" stroke="rgba(220, 212, 240, 0.06)" strokeWidth="1" strokeLinecap="round" />
        <path d="M53 82 C53 72, 62 68, 72 68 C81 68, 87 74, 87 82" fill="none" stroke="#000000" strokeWidth="1.2" />
        <path d="M112 82 C112 74, 118 68, 128 68 C138 68, 148 72, 148 82 C148 90, 140 94, 130 94 C120 94, 112 90, 112 82Z" fill="url(#g-eye)" stroke="rgba(200, 190, 230, 0.10)" strokeWidth="1.2" />
        <path d="M115 86 C120 92, 140 92, 145 86" fill="none" stroke="rgba(220, 212, 240, 0.06)" strokeWidth="1" strokeLinecap="round" />
        <path d="M113 82 C113 74, 119 68, 128 68 C137 68, 147 72, 147 82" fill="none" stroke="#000000" strokeWidth="1.2" />
      </svg>
      {showText && (
        <span style={{ fontFamily: "'Cinzel', serif" }} className="text-xl font-bold tracking-widest text-[#ede8f2] uppercase leading-none">
          Moretta
        </span>
      )}
    </div>
  );
};

export default Logo;
