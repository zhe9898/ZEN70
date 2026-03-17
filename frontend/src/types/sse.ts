/** 硬件事件：path、state、reason */
export interface HardwareEvent {
  type?: string;
  path?: string;
  state?: string;
  reason?: string;
}

/** 软开关事件 */
export interface SwitchEvent {
  name?: string;
  state?: string;
  reason?: string;
}

export interface BoardEvent {
  action?: string;
  message_id?: string;
  author?: string;
}

export interface SSEEvent {
  type: string;
  data: HardwareEvent | SwitchEvent | BoardEvent;
}
