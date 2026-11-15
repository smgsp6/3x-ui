// Vite resolves image imports to hashed asset URLs; no file contents are embedded.
declare module '*.png' {
  const url: string;
  export default url;
}
