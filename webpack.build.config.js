var WebpackConfig = require('./helper/webpack-config');

module.exports = WebpackConfig({
  hot: false,
  hash: false,
  debug: false,
  optimize: true,
  saveStats: true,
  failOnError: true
});