"use client";

import {
  ACCENT,
  INK,
  LINE,
  MUTE,
  PRIMARY,
  SOFT,
  Stage,
  ease,
  easeOut,
  font,
  lerp,
  seg,
  useLoop,
  type Play,
} from "@/components/blog/Figure";

const SVG_STYLE = { width: "100%", height: "auto", display: "block" } as const;

function SourcePipelineScene(play: Play) {
  const { t } = useLoop(play, 8, .74);
  const travel = ease(seg(t, 0, .62));
  const validate = easeOut(seg(t, .15, .32));
  const canonical = easeOut(seg(t, .35, .53));
  const served = easeOut(seg(t, .57, .72));
  const fade = 1 - seg(t, .95, 1);
  const packetX = lerp(132, 593, travel);
  const stages = [
    { x: 174, title: "Validate", note: "Source schema" },
    { x: 332, title: "Canonicalise", note: "Entities + edges" },
    { x: 516, title: "Publish", note: "Serving record" },
  ];

  return (
    <svg viewBox="0 0 700 260" style={SVG_STYLE}>
      <g opacity={fade}>
        <text x={20} y={28} fontSize={13} fill={MUTE} style={font}>Independent source records</text>
        {[
          ["GLEIF", 54], ["SEC filings", 91], ["Public registers", 128],
        ].map(([label, y], index) => (
          <g key={label as string} opacity={easeOut(seg(t, index * .025, .12 + index * .025))}>
            <rect x={20} y={Number(y)} width={112} height={28} rx={8} fill={SOFT} />
            <text x={34} y={Number(y) + 18} fontSize={12} fill={INK} style={font}>{label}</text>
          </g>
        ))}
        <path d="M132 105 H630" stroke={LINE} strokeWidth={2} />
        {stages.map((stage, index) => {
          const reveal = index === 0 ? validate : index === 1 ? canonical : served;
          return (
            <g key={stage.title} opacity={.35 + reveal * .65}>
              <rect x={stage.x} y={72} width={128} height={72} rx={10} fill="#fff" stroke={index === 2 && served > .8 ? PRIMARY : LINE} strokeWidth={index === 2 && served > .8 ? 2 : 1} />
              <circle cx={stage.x + 18} cy={91} r={5} fill={reveal > .6 ? ACCENT : "#cfcbc5"} />
              <text x={stage.x + 16} y={116} fontSize={13} fontWeight={650} fill={INK} style={font}>{stage.title}</text>
              <text x={stage.x + 16} y={134} fontSize={11} fill={MUTE} style={font}>{stage.note}</text>
            </g>
          );
        })}
        <circle cx={packetX} cy={105} r={6} fill={ACCENT} />
        <g opacity={served} transform={`translate(0 ${lerp(8, 0, served)})`}>
          <rect x={404} y={181} width={226} height={48} rx={9} fill={SOFT} />
          <text x={420} y={201} fontSize={12} fill={MUTE} style={font}>Runtime reads</text>
          <text x={420} y={219} fontSize={13} fontWeight={650} fill={INK} style={font}>One document shaped for the profile</text>
        </g>
      </g>
    </svg>
  );
}

export function SourcePipelineFigure() {
  return (
    <Stage
      alt="GLEIF, SEC filings and public registers enter independently. A record moves through source validation, canonical entities and typed edges, then into a serving record shaped for runtime profile reads."
      caption="The serving layer is disposable: rebuilding it from Parquet must lose nothing."
    >
      {(play) => <SourcePipelineScene {...play} />}
    </Stage>
  );
}

function ResolutionScene(play: Play) {
  const { t } = useLoop(play, 8.5, .78);
  const query = easeOut(seg(t, 0, .14));
  const retrieve = easeOut(seg(t, .12, .31));
  const score = ease(seg(t, .31, .56));
  const compare = easeOut(seg(t, .55, .68));
  const decide = easeOut(seg(t, .68, .78));
  const fade = 1 - seg(t, .95, 1);
  const candidates = [
    { name: "Acme Opportunities Fund II", value: .92 },
    { name: "Acme Opportunities Feeder II", value: .89 },
    { name: "Acme Opportunities Fund III", value: .54 },
  ];

  return (
    <svg viewBox="0 0 700 285" style={SVG_STYLE}>
      <g opacity={fade}>
        <g opacity={query} transform={`translate(${lerp(-18, 0, query)} 0)`}>
          <rect x={30} y={24} width={640} height={43} rx={11} fill="#fff" stroke={LINE} />
          <circle cx={51} cy={45} r={7} fill="none" stroke={PRIMARY} strokeWidth={1.5} />
          <path d="M56 50l5 5" stroke={PRIMARY} strokeWidth={1.5} />
          <text x={75} y={50} fontSize={14} fill={INK} style={font}>Acme global opportunities fund 2</text>
        </g>
        <text x={30} y={94} fontSize={12} fill={MUTE} style={font} opacity={retrieve}>Candidate retrieval</text>
        {candidates.map((candidate, index) => {
          const row = easeOut(seg(t, .15 + index * .04, .3 + index * .04));
          const width = 230 * candidate.value * score;
          return (
            <g key={candidate.name} opacity={row} transform={`translate(${lerp(18, 0, row)} 0)`}>
              <text x={30} y={126 + index * 43} fontSize={12} fill={INK} style={font}>{candidate.name}</text>
              <rect x={330} y={112 + index * 43} width={230} height={16} rx={8} fill={SOFT} />
              <rect x={330} y={112 + index * 43} width={width} height={16} rx={8} fill={index < 2 ? "#cfcbc5" : "#e8e5e0"} />
              <text x={574} y={125 + index * 43} fontSize={12} fill={MUTE} style={font} opacity={score}>{Math.round(candidate.value * 100)}</text>
            </g>
          );
        })}
        <g opacity={compare}>
          <path d="M548 112 H574 M548 155 H574 M568 112 V155" fill="none" stroke={PRIMARY} strokeWidth={1.5} />
          <text x={584} y={145} fontSize={12} fill={PRIMARY} style={font}>gap 3</text>
        </g>
        <g opacity={decide} transform={`translate(0 ${lerp(10, 0, decide)})`}>
          <rect x={30} y={246} width={640} height={27} rx={13.5} fill={SOFT} />
          <rect x={30} y={246} width={83} height={27} rx={13.5} fill={ACCENT} />
          <text x={71.5} y={264} textAnchor="middle" fontSize={12} fontWeight={700} fill="#fff" style={font}>Review</text>
          <text x={128} y={264} fontSize={12} fill={INK} style={font}>Two candidates are too close. Do not guess.</text>
        </g>
      </g>
    </svg>
  );
}

export function ResolutionFigure() {
  return (
    <Stage
      alt="A fund name retrieves three similar candidates. Their deterministic scores grow to 92, 89 and 54. A bracket reveals a gap of only 3 between the top two, so the decision becomes Review instead of an automatic match."
      caption="A high score asks whether one candidate looks right. The runner-up gap asks whether another looks almost as right."
    >
      {(play) => <ResolutionScene {...play} />}
    </Stage>
  );
}

function QueryPathsScene(play: Play) {
  const { t } = useLoop(play, 7.5, .76);
  const ask = easeOut(seg(t, 0, .14));
  const split = ease(seg(t, .14, .34));
  const work = easeOut(seg(t, .34, .58));
  const join = easeOut(seg(t, .58, .74));
  const fade = 1 - seg(t, .95, 1);
  const dash = lerp(70, 0, split);

  return (
    <svg viewBox="0 0 700 285" style={SVG_STYLE}>
      <g opacity={fade}>
        <g opacity={ask}>
          <rect x={190} y={18} width={320} height={42} rx={11} fill={SOFT} />
          <text x={350} y={44} textAnchor="middle" fontSize={14} fill={INK} style={font}>Who ultimately manages this fund?</text>
        </g>
        <path d="M350 60 V86 H176 V108 M350 86 H524 V108" fill="none" stroke={LINE} strokeWidth={2} strokeDasharray="70" strokeDashoffset={dash} />
        <g opacity={split}>
          <rect x={50} y={108} width={252} height={91} rx={10} fill="#fff" stroke={LINE} />
          <text x={70} y={134} fontSize={12} fill={PRIMARY} fontWeight={700} style={font}>Search</text>
          <text x={70} y={160} fontSize={14} fill={INK} style={font}>Resolve and inspect</text>
          <text x={70} y={181} fontSize={11} fill={MUTE} style={font}>Candidates → selected profile</text>
          <rect x={398} y={108} width={252} height={91} rx={10} fill="#fff" stroke={LINE} />
          <text x={418} y={134} fontSize={12} fill={PRIMARY} fontWeight={700} style={font}>Agent</text>
          <text x={418} y={160} fontSize={14} fill={INK} style={font}>Investigate and explain</text>
          <text x={418} y={181} fontSize={11} fill={MUTE} style={font}>Model → MCP tools → evidence</text>
        </g>
        {[0, 1, 2].map((index) => <circle key={`left-${index}`} cx={90 + index * 40} cy={190} r={4 + work * 2} fill={index === Math.floor(work * 3) % 3 ? ACCENT : "#dcd8d2"} opacity={work} />)}
        {[0, 1, 2, 3].map((index) => <circle key={`right-${index}`} cx={438 + index * 40} cy={190} r={4 + work * 2} fill={index === Math.floor(work * 4) % 4 ? ACCENT : "#dcd8d2"} opacity={work} />)}
        <path d="M176 199 V220 H350 M524 199 V220 H350 V235" fill="none" stroke={LINE} strokeWidth={2} strokeDasharray="90" strokeDashoffset={lerp(90, 0, join)} />
        <g opacity={join} transform={`translate(0 ${lerp(8, 0, join)})`}>
          <rect x={206} y={235} width={288} height={36} rx={9} fill={SOFT} />
          <circle cx={228} cy={253} r={5} fill={ACCENT} />
          <text x={243} y={257} fontSize={13} fontWeight={650} fill={INK} style={font}>The same canonical serving records</text>
        </g>
      </g>
    </svg>
  );
}

export function QueryPathsFigure() {
  return (
    <Stage
      alt="One institutional question splits into two paths. Search resolves candidates and opens a selected profile. Agent mode plans, calls MCP tools and collects evidence. Both paths join at the same canonical serving records."
      caption="The interface changes. The identity and relationship logic underneath it does not."
    >
      {(play) => <QueryPathsScene {...play} />}
    </Stage>
  );
}

function EvidenceGateScene(play: Play) {
  const { t } = useLoop(play, 8, .79);
  const tool = easeOut(seg(t, 0, .19));
  const draft = easeOut(seg(t, .18, .37));
  const replay = ease(seg(t, .38, .63));
  const answer = easeOut(seg(t, .65, .78));
  const fade = 1 - seg(t, .95, 1);
  const stages = [66, 241, 416, 591];

  return (
    <svg viewBox="0 0 700 265" style={SVG_STYLE}>
      <g opacity={fade}>
        <text x={20} y={28} fontSize={13} fill={MUTE} style={font}>One numeric claim, from lookup to rendered answer</text>
        <path d="M90 126 H610" stroke={LINE} strokeWidth={2} />
        {[tool, draft, replay, answer].map((opacity, index) => <circle key={stages[index]} cx={stages[index]} cy={126} r={6} fill={opacity > .7 ? ACCENT : "#dcd8d2"} />)}
        <g opacity={tool} transform={`translate(0 ${lerp(8, 0, tool)})`}>
          <rect x={20} y={55} width={140} height={61} rx={9} fill="#fff" stroke={LINE} />
          <text x={34} y={78} fontSize={12} fill={PRIMARY} fontWeight={700} style={font}>Tool result</text>
          <text x={34} y={99} fontSize={12} fill={INK} style={font}>f_171 = 171</text>
        </g>
        <g opacity={draft} transform={`translate(0 ${lerp(8, 0, draft)})`}>
          <rect x={195} y={55} width={140} height={61} rx={9} fill="#fff" stroke={LINE} />
          <text x={209} y={78} fontSize={12} fill={PRIMARY} fontWeight={700} style={font}>Draft</text>
          <text x={209} y={99} fontSize={11} fill={INK} style={font}>{"{{f:f_171}} securities"}</text>
        </g>
        <g opacity={replay} transform={`translate(0 ${lerp(8, 0, replay)})`}>
          <rect x={370} y={55} width={140} height={61} rx={9} fill={replay > .75 ? SOFT : "#fff"} stroke={replay > .75 ? PRIMARY : LINE} />
          <text x={384} y={78} fontSize={12} fill={PRIMARY} fontWeight={700} style={font}>Replay source</text>
          <text x={384} y={99} fontSize={11} fill={INK} style={font}>Same address, same value</text>
          <path d={`M378 ${lerp(63, 108, replay)} H502`} stroke={PRIMARY} strokeWidth={1.5} opacity={seg(t, .42, .61)} />
        </g>
        <g opacity={answer} transform={`translate(0 ${lerp(8, 0, answer)})`}>
          <rect x={545} y={55} width={135} height={61} rx={9} fill="#fff" stroke={PRIMARY} strokeWidth={1.5} />
          <text x={559} y={78} fontSize={12} fill={PRIMARY} fontWeight={700} style={font}>Rendered</text>
          <text x={559} y={99} fontSize={12} fill={INK} style={font}>171 securities [3]</text>
        </g>
        <g opacity={answer}>
          <rect x={111} y={174} width={478} height={50} rx={10} fill={SOFT} />
          <text x={350} y={195} textAnchor="middle" fontSize={12} fill={MUTE} style={font}>The model never gets to type the final number.</text>
          <text x={350} y={214} textAnchor="middle" fontSize={13} fontWeight={650} fill={INK} style={font}>The gate renders it only after the lookup repeats.</text>
        </g>
      </g>
    </svg>
  );
}

export function EvidenceGateFigure() {
  return (
    <Stage
      alt="An MCP tool returns an addressed fact named f_171 with value 171. The draft answer contains only the fact placeholder. The submission gate replays the source address, confirms the same value, and then renders 171 securities with citation 3."
      caption="Citations prove where a claim came from. Fact replay proves the value still comes back."
    >
      {(play) => <EvidenceGateScene {...play} />}
    </Stage>
  );
}
