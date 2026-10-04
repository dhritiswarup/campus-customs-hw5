import type { AgentName } from "./types";

export interface AgentMeta {
  name: AgentName;
  label: string;
  role: string;
  color: string;
  icon: (props: { size?: number }) => React.ReactElement;
}

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const Crown = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...stroke}>
    <path d="M3 8l4.5 4L12 5l4.5 7L21 8l-2 11H5L3 8z" />
    <path d="M7 16h10" />
  </svg>
);
const Box = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...stroke}>
    <path d="M21 8l-9-5-9 5 9 5 9-5z" />
    <path d="M3 8v8l9 5 9-5V8" />
    <path d="M12 13v8" />
  </svg>
);
const Coins = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...stroke}>
    <ellipse cx="9" cy="6" rx="6" ry="2.6" />
    <path d="M3 6v4c0 1.4 2.7 2.6 6 2.6s6-1.2 6-2.6V6" />
    <path d="M3 10v4c0 1.4 2.7 2.6 6 2.6" />
    <ellipse cx="15.5" cy="15" rx="5.5" ry="2.4" />
    <path d="M10 15v3.4c0 1.3 2.5 2.4 5.5 2.4s5.5-1.1 5.5-2.4V15" />
  </svg>
);
const Key = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...stroke}>
    <path d="M4 21V10l8-6 8 6v11" />
    <path d="M9 21v-6h6v6" />
    <circle cx="12" cy="10.5" r="1.4" />
  </svg>
);
const Chat = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...stroke}>
    <path d="M4 5h16v11H9l-5 4V5z" />
    <path d="M8 9.5h8M8 12.5h5" />
  </svg>
);

export const AGENTS: Record<AgentName, AgentMeta> = {
  boss: { name: "boss", label: "The Boss", role: "Runs the board", color: "#00356b", icon: Crown },
  inventory: { name: "inventory", label: "Inventory", role: "Stock & vendors", color: "#0e9f8e", icon: Box },
  accounting: { name: "accounting", label: "Accounting", role: "Cash & pricing", color: "#c98700", icon: Coins },
  facilities: { name: "facilities", label: "Facilities", role: "Lease & rent", color: "#7357e0", icon: Key },
  customer_service: { name: "customer_service", label: "Customer Service", role: "Customer replies", color: "#e2583a", icon: Chat },
};

export const AGENT_ORDER: AgentName[] = ["boss", "inventory", "accounting", "facilities", "customer_service"];

export function agentMeta(name: string | null | undefined): AgentMeta {
  return (name && AGENTS[name as AgentName]) || AGENTS.boss;
}
