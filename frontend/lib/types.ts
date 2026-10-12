export interface User {
  id: string;
  name: string;
  email: string;
  role: 'customer' | 'admin';
}
export interface Product {
  id: string;
  name: string;
  category: string;
  description: string;
  price_cents: number;
  stock: number;
  active: number;
  image: string;
  specs: Record<string, string>;
  quantity?: number;
  restock_at?: string | null;
}
export interface Cart {
  items: Product[];
  subtotal_cents: number;
  shipping_cents: number;
  total_cents: number;
}
export interface Order {
  id: string;
  user_id: string;
  status: string;
  total_cents: number;
  address: string;
  created_at: string;
  items: {
    product_id: string;
    name: string;
    price_cents: number;
    quantity: number;
  }[];
  fulfillment: {
    id: string;
    stage: string;
    detail: string;
    created_at: string;
  }[];
}
export interface Ticket {
  id: string;
  user_id: string;
  order_id: string | null;
  reason: string;
  status: string;
  resolution: string;
  created_at: string;
  conversation_id: string | null;
  category: string;
  summary: string;
  owner_id: string | null;
  owner_name: string | null;
  due_at: string | null;
  events: { id: string; kind: string; content: string; created_at: string }[];
}
export interface Source {
  id: string;
  title: string;
  content: string;
  score: number;
}
export interface Action {
  id: string;
  summary: string;
  kind: string;
  status: string;
  expires_at: number;
  preview?: {
    before: Record<string, unknown> | null;
    after: Record<string, unknown>;
  };
}
export interface ProductEvent {
  id: string;
  product_id: string;
  actor_name: string;
  kind: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown>;
  action_id: string | null;
  created_at: string;
}
export interface Step {
  node: string;
  status: string;
  detail: string;
}
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  actions?: Action[];
  products?: Product[];
  steps?: Step[];
  elapsed_ms?: number;
  first_response_ms?: number | null;
  llm_calls?: number;
  tool_calls?: number;
  mode?: string;
  author?: string;
  trace?: { node: string; ok?: boolean; elapsed_ms?: number; error?: string }[];
}
export interface Conversation {
  id: string;
  title: string;
}
export interface AIRun {
  id: string;
  mode: string;
  elapsed_ms: number;
  first_response_ms: number | null;
  llm_calls: number;
  tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  status: string;
  created_at: string;
  trace: string;
}
export interface CustomerContext {
  customer: User;
  orders: Order[];
  tickets: Ticket[];
  conversations: Conversation[];
}
export interface StreamEvent {
  event: string;
  data: unknown;
}
