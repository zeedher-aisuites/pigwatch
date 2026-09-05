export function supportsWebGL(): boolean {
  if (typeof window === "undefined" || typeof window.WebGLRenderingContext === "undefined") {
    return false;
  }
  try {
    const canvas = document.createElement("canvas");
    const options: WebGLContextAttributes = {
      failIfMajorPerformanceCaveat: true,
      powerPreference: "high-performance",
    };
    const context = canvas.getContext("webgl2", options) ?? canvas.getContext("webgl", options);
    if (context === null) {
      return false;
    }
    context.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}
