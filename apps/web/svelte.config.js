import adapter from '@sveltejs/adapter-auto';

const config = {
  kit: {
    adapter,
    alias: {
      $lib: 'src/lib'
    }
  }
};

export default config;
