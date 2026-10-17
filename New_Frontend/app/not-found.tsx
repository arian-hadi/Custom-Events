export default function NotFound() {
  return <main className="tw:flex tw:min-h-screen tw:flex-col tw:items-center tw:justify-center tw:gap-6 tw:bg-black tw:px-6 tw:text-center tw:text-white">
    <p className="tw:text-lg tw:text-amber-400">404</p>
    <h1 className="tw:text-5xl tw:font-bold">Page not found</h1>
    <a href="/" className="tw:rounded-xl tw:border tw:border-white tw:px-8 tw:py-4 tw:font-bold tw:transition-colors tw:hover:bg-white tw:hover:text-black">Back to home</a>
  </main>;
}
