declare module 'simple-mind-map' {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export default class MindMap {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    constructor(options: Record<string, any>)
    on(event: string, handler: (...args: any[]) => void): void
    off(event: string, handler: (...args: any[]) => void): void
    setData(data: unknown): void
    render(callback?: () => void): void
    resize(): void
    destroy(): void
    setFullData(...args: unknown[]): void
  }
}
