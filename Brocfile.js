/*
       Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.
*/
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
