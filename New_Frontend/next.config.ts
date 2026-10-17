import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'standalone',
  skipTrailingSlashRedirect: true,
  images: {unoptimized:true},
  devIndicators: false,
  // Docker binds Next to 0.0.0.0; both loopback browser origins may use HMR.
  allowedDevOrigins: ['127.0.0.1'],
  async rewrites() {
    // Browser requests stay on one origin so Django sessions and CSRF work.
    // Docker's gateway handles these paths before they reach Next.js.
    const backend = (process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
    const prefixes = ['api', 'media', 'static', 'admin', 'accounts', 'dashboard', 'shop', 'summernote', 'ckeditor5', 'legacy', 'about', 'terms', 'privacy', 'disclaimers', 'editinghub', 'announcements'];
    return { beforeFiles: [
      ...prefixes.map(prefix => ({ source: `/${prefix}/:path*`, destination: `${backend}/${prefix}/:path*${['media', 'static'].includes(prefix) ? '' : '/'}` })),
      { source: '/notifications/api/:path*', destination: `${backend}/notifications/api/:path*/` },
      { source: '/notifications/unread-count/:path*', destination: `${backend}/notifications/unread-count/:path*/` },
      { source: '/notifications/mark-all-read/:path*', destination: `${backend}/notifications/mark-all-read/:path*/` },
      { source: '/notifications/:id(\\d+)/:action(read|delete)/', destination: `${backend}/notifications/:id/:action/` },
      { source: '/events/events/:path*', destination: `${backend}/events/events/:path*/` },
      ...['create', 'add-fields', 'finish'].map(action => ({ source: `/events/${action}/:path*`, destination: `${backend}/events/${action}/:path*/` })),
    ] };
  },
};

export default nextConfig;
