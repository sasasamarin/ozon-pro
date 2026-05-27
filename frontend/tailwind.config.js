/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#ffffff',
        'bg-subtle': '#fafafa',
        surface: '#ffffff',
        border: {
          DEFAULT: '#e4e4e7',
          subtle: '#f4f4f5',
        },
        fg: {
          DEFAULT: '#09090b',
          muted: '#52525b',
          subtle: '#a1a1aa',
        },
        accent: {
          DEFAULT: '#18181b',
          hover: '#27272a',
        },
        success: '#16a34a',
        error: '#dc2626',
        warning: '#ca8a04',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        xs: ['12px', { lineHeight: '16px', letterSpacing: '0.01em' }],
        sm: ['13px', { lineHeight: '18px' }],
        base: ['14px', { lineHeight: '20px' }],
        lg: ['16px', { lineHeight: '24px' }],
        xl: ['18px', { lineHeight: '26px' }],
        '2xl': ['24px', { lineHeight: '32px', letterSpacing: '-0.01em' }],
        '3xl': ['32px', { lineHeight: '40px', letterSpacing: '-0.02em' }],
      },
      borderRadius: {
        sm: '6px',
        DEFAULT: '8px',
        md: '8px',
        lg: '12px',
        xl: '16px',
        '2xl': '20px',
      },
      backgroundImage: {
        'aurora': [
          'radial-gradient(at 18% 22%, rgba(254, 205, 211, 0.55) 0px, transparent 50%)',
          'radial-gradient(at 78% 28%, rgba(199, 210, 254, 0.65) 0px, transparent 48%)',
          'radial-gradient(at 65% 82%, rgba(254, 240, 199, 0.55) 0px, transparent 52%)',
          'radial-gradient(at 25% 75%, rgba(207, 250, 254, 0.5) 0px, transparent 48%)',
          'linear-gradient(180deg, #fafafa 0%, #ffffff 100%)',
        ].join(', '),
        'aurora-soft':
          'radial-gradient(circle at 100% 0%, rgba(244, 114, 182, 0.07), transparent 55%), radial-gradient(circle at 0% 100%, rgba(99, 102, 241, 0.06), transparent 55%)',
        'grid-faint':
          "url(\"data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40' fill='none'%3e%3cpath d='M.5 40V.5H40' stroke='%23a1a1aa' stroke-opacity='0.18'/%3e%3c/svg%3e\")",
        'dot-faint':
          "url(\"data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3e%3ccircle cx='1' cy='1' r='1' fill='%23a1a1aa' fill-opacity='0.25'/%3e%3c/svg%3e\")",
      },
      boxShadow: {
        glass:
          '0 1px 2px 0 rgb(0 0 0 / 0.04), 0 8px 28px -10px rgb(0 0 0 / 0.10)',
        elev:
          '0 0 0 1px rgb(0 0 0 / 0.04), 0 1px 2px 0 rgb(0 0 0 / 0.04), 0 12px 24px -8px rgb(0 0 0 / 0.06)',
      },
      animation: {
        'fade-in': 'fadeIn 200ms ease-out',
        'slide-up': 'slideUp 300ms ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
