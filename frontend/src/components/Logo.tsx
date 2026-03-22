import React from 'react';

interface LogoProps {
  className?: string;
  size?: number | string;
  showText?: boolean;
}

const Logo: React.FC<LogoProps> = ({ className = '', size = 48, showText = false }) => {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <svg
        width={size}
        height={(Number(size) || 48) * (200 / 180)}
        viewBox="10 0 180 200"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="drop-shadow-lg"
      >
        <defs>
          <radialGradient id="gf_logo" cx="50%" cy="30%" r="70%">
            <stop offset="0%" stopColor="#322a40" />
            <stop offset="40%" stopColor="#1f1a29" />
            <stop offset="75%" stopColor="#110e17" />
            <stop offset="100%" stopColor="#050407" />
          </radialGradient>
          <radialGradient id="g-form_logo" cx="50%" cy="40%" r="70%" fx="50%" fy="30%">
            <stop offset="0%" stopColor="rgba(180, 160, 220, 0.08)" />
            <stop offset="100%" stopColor="rgba(180, 160, 220, 0)" />
          </radialGradient>
          <radialGradient id="g-nose_logo" cx="50%" cy="45%" r="40%" fx="50%" fy="35%">
            <stop offset="0%" stopColor="rgba(200, 190, 240, 0.07)" />
            <stop offset="100%" stopColor="rgba(200, 190, 240, 0)" />
          </radialGradient>
          <linearGradient id="g-eye_logo" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#020103" />
            <stop offset="100%" stopColor="#161221" />
          </linearGradient>
        </defs>

        {/* Base Shape */}
        <path d="M100 10 C72 10,47 30,35 60 C25 90,25 115,35 140 C45 165,68 180,82 185 C92 188,108 188,118 185 C132 180,155 165,165 140 C175 115,175 90,165 60 C155 30,128 10,100 10Z" fill="url(#gf_logo)" />
        <path d="M100 10 C72 10,47 30,35 60 C25 90,25 115,35 140 C45 165,68 180,82 185 C92 188,108 188,118 185 C132 180,155 165,165 140 C175 115,175 90,165 60 C155 30,128 10,100 10Z" fill="url(#g-form_logo)" />
        
        {/* Nose */}
        <ellipse cx="100" cy="95" rx="8" ry="40" fill="url(#g-nose_logo)" />
        
        {/* Eyes */}
        <path d="M52 82 C52 72, 62 68, 72 68 C82 68, 88 74, 88 82 C88 90, 80 94, 70 94 C60 94, 52 90, 52 82Z" fill="url(#g-eye_logo)" />
        <path d="M112 82 C112 74, 118 68, 128 68 C138 68, 148 72, 148 82 C148 90, 140 94, 130 94 C120 94, 112 90, 112 82Z" fill="url(#g-eye_logo)" />
        
        {/* Mouth */}
        <ellipse cx="100" cy="150" rx="10" ry="3" fill="#000" />
      </svg>
      {showText && (
        <span className="font-display text-xl font-bold tracking-widest text-[#ede8f2] uppercase">
          Moretta
        </span>
      )}
    </div>
  );
};

export default Logo;
