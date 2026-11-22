/** Minimal typed event emitter shared by the Socket.IO adapter and the mock backend. */
export class Emitter<Events extends object> {
  private readonly handlers = new Map<keyof Events, Set<(payload: never) => void>>();

  /** Register a handler; returns the unsubscribe function. */
  on<K extends keyof Events>(event: K, handler: (payload: Events[K]) => void): () => void {
    const set = this.handlers.get(event) ?? new Set();
    set.add(handler as (payload: never) => void);
    this.handlers.set(event, set);
    return () => {
      set.delete(handler as (payload: never) => void);
    };
  }

  /** Call every handler registered for `event`. */
  emit<K extends keyof Events>(event: K, payload: Events[K]): void {
    this.handlers.get(event)?.forEach((handler) => {
      (handler as (p: Events[K]) => void)(payload);
    });
  }
}
