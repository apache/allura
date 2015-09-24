var babelTranspiler = require("broccoli-babel-transpiler");
var sourceMap = require('broccoli-source-map');
var concat = require('broccoli-concat');
var funnel = require('broccoli-funnel');
var uglifyJavaScript = require('broccoli-uglify-js');

var tree = funnel('Allura/allura/public/nf/js', {
  include: ['*.es6.js'],
});
tree = babelTranspiler(tree, {
    browserPolyfill: true,
    //filterExtensions:['es6.js'],
    sourceMaps: 'inline',  // external doesn't work, have to use extract below
    comments: false,
});
tree = concat(tree, {
  inputFiles: ['**/*.js'],
  outputFile: '/transpiled.js'
});
tree = sourceMap.extract(tree);

if (process.env.BROCCOLI_ENV === 'production') {
    /* can't use this for dev mode, since it drops the sourcemap comment even if we set  output: {comments: true}
     https://github.com/mishoo/UglifyJS2/issues/653
     https://github.com/mishoo/UglifyJS2/issues/754
     https://github.com/mishoo/UglifyJS2/issues/780
     https://github.com/mishoo/UglifyJS2/issues/520
     */
    tree = uglifyJavaScript(tree, {
        mangle: false,
        compress: false
    });
}

module.exports = tree;
