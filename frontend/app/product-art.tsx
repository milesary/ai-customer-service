// Local product illustrations keep the demo usable without remote image services.
export default function ProductArt({ kind }: { kind: string }) {
  const common = {
    stroke: '#253d35',
    strokeWidth: 3,
    strokeLinejoin: 'round' as const,
  };
  return (
    <svg
      viewBox="0 0 320 220"
      aria-hidden="true"
      className={`product-art art-${kind}`}
    >
      <ellipse cx="160" cy="186" rx="83" ry="10" fill="#17392d" opacity=".09" />
      {kind === 'shirt' && (
        <g {...common}>
          <path
            d="M131 45c5 22 53 22 58 0l30 10 38 42-30 24-21-23v79H114V98l-21 23-30-24 38-42Z"
            fill="#d7dfd5"
          />
          <path
            d="M131 45c5 22 53 22 58 0"
            fill="none"
            stroke="#7e9283"
            strokeWidth="6"
          />
          <path d="M120 167h80" stroke="#7e9283" strokeWidth="2" />
        </g>
      )}
      {kind === 'headphones' && (
        <g {...common}>
          <path
            d="M93 135V100a67 67 0 0 1 134 0v35"
            fill="none"
            strokeWidth="19"
          />
          <path
            d="M93 105V100a67 67 0 0 1 134 0v5"
            fill="none"
            stroke="#859b8e"
            strokeWidth="8"
          />
          <rect x="77" y="103" width="39" height="71" rx="17" fill="#395d4e" />
          <rect x="204" y="103" width="39" height="71" rx="17" fill="#395d4e" />
          <path d="M109 111v53m102-53v53" stroke="#9bb0a4" strokeWidth="4" />
        </g>
      )}
      {kind === 'keyboard' && (
        <g transform="translate(37 65) rotate(-7 120 55)" {...common}>
          <rect width="246" height="103" rx="10" fill="#d3dbd5" />
          <rect x="8" y="9" width="230" height="86" rx="5" fill="#85978c" />
          {Array.from({ length: 4 }, (_, r) =>
            Array.from({ length: 12 }, (_, c) => (
              <rect
                key={`${r}-${c}`}
                x={13 + c * 18.5}
                y={14 + r * 18}
                width="15"
                height="14"
                rx="2"
                fill={c === 11 ? '#335e49' : '#eff2ed'}
                strokeWidth=".6"
              />
            )),
          )}
          <rect
            x="66"
            y="70"
            width="90"
            height="14"
            rx="2"
            fill="#eff2ed"
            strokeWidth=".6"
          />
        </g>
      )}
      {kind === 'charger' && (
        <g {...common}>
          <path d="M159 153c0 35 80 15 104 31" fill="none" stroke="#74857b" />
          <ellipse cx="150" cy="135" rx="78" ry="34" fill="#2c4c3c" />
          <ellipse cx="150" cy="125" rx="78" ry="34" fill="#d2ddd2" />
          <ellipse
            cx="150"
            cy="125"
            rx="61"
            ry="25"
            fill="#edf1e9"
            strokeWidth="1"
          />
          <path d="m155 108-15 19h18l-13 16" fill="none" strokeWidth="2" />
        </g>
      )}
      {kind === 'speaker' && (
        <g {...common}>
          <rect
            x="101"
            y="59"
            width="118"
            height="121"
            rx="34"
            fill="#7c9689"
          />
          <rect x="106" y="76" width="108" height="99" rx="28" fill="#3e6050" />
          {Array.from({ length: 8 }, (_, r) =>
            Array.from({ length: 10 }, (_, c) => (
              <circle
                key={`${r}-${c}`}
                cx={120 + c * 9}
                cy={91 + r * 10}
                r="1.5"
                fill="#9fb1a3"
                stroke="none"
              />
            )),
          )}
          <path d="M137 60c0-24 46-24 46 0" fill="none" strokeWidth="7" />
          <path d="M148 65h24" stroke="#dae3d9" strokeWidth="2" />
        </g>
      )}
      {kind === 'mouse' && (
        <g {...common}>
          <path
            d="M116 150c-9-23-15-68 11-95 17-17 50-20 70-1 24 23 27 61 15 93-18 47-82 50-96 3Z"
            fill="#d7dfd5"
          />
          <path
            d="M166 42v68m-51 12c20-10 65-16 101-2"
            fill="none"
            stroke="#7e9283"
            strokeWidth="2"
          />
          <rect x="158" y="62" width="13" height="29" rx="6" fill="#3f5d49" />
        </g>
      )}
      {kind === 'hub' && (
        <g transform="rotate(-10 160 120)" {...common}>
          <path
            d="M110 92c-20-26-68-10-68-43"
            fill="none"
            stroke="#7b8d83"
            strokeWidth="7"
          />
          <rect x="94" y="80" width="163" height="73" rx="12" fill="#b9c8bf" />
          <path d="M101 135h148" stroke="#7a9082" strokeWidth="1" />
          <rect x="117" y="112" width="27" height="10" rx="2" fill="#294238" />
          <rect x="154" y="112" width="27" height="10" rx="2" fill="#294238" />
          <rect x="198" y="111" width="35" height="12" rx="3" fill="#294238" />
          <text
            x="148"
            y="102"
            fill="#546b5b"
            stroke="none"
            fontSize="10"
            letterSpacing="3"
          >
            SHOPPING
          </text>
        </g>
      )}
    </svg>
  );
}
