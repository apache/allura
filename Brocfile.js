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
var sourceMapConcat = require('broccoli-sourcemap-concat');
var funnel = require('broccoli-funnel');
var uglifyJavaScript = require('broccoli-uglify-js');
var mergeTrees = require('broccoli-merge-trees');

var production = (process.env.BROCCOLI_ENV === 'production' || process.env.NODE_ENV === 'production');

/* main output tree */
var tree = funnel('Allura/allura/public/nf/js', {
    include: ['*.es6.js'],
});
tree = babelTranspiler(tree, {
    //filterExtensions:['es6.js'],
    sourceMaps: 'inline',  // external doesn't work, but sourceMapConcat will extract them
    comments: false,
});
tree = sourceMapConcat(tree, {
    inputFiles: ['**/*'],
    outputFile: '/transpiled.js'
});

/* exactly what's needed for the navbar, so separate apps may use it too */
var react_file = 'public/nf/js/react.' + (production ? 'production.min' : 'development') + '.js';
var react_dom_file = 'public/nf/js/react-dom.' + (production ? 'production.min' : 'development') + '.js';
var navbar = funnel('Allura/allura', {
    include: ['public/nf/js/underscore-1.13.6.min.js',
              react_file,
              react_dom_file,
              'public/nf/js/create-react-class.min.js',
              'public/nf/js/prop-types.min.js',
              'public/nf/js/react-drag.min.js',
              'public/nf/js/react-reorderable.min.js',
              'lib/widgets/resources/js/jquery.lightbox_me.js',
              'public/nf/js/browser-polyfill.min.js',
              'public/nf/js/admin_modal.js',
              'public/nf/js/jquery.tooltipster.js',
              'public/nf/js/navbar.es6.js',
              'public/nf/js/context-menu.es6.js',
              'public/nf/js/tooltip.es6.js'
    ],
});
navbar = babelTranspiler(navbar, {
    filterExtensions:['es6.js'],
    sourceMaps: 'inline',  // external doesn't work, but sourceMapConcat will extract them
    comments: false,
});
var navbar = sourceMapConcat(navbar, {
    // headerFiles & footerFiles used to specify some that must come before or after others
    headerFiles: [react_file,
                  react_dom_file,
                  'public/nf/js/create-react-class.min.js',
                  'public/nf/js/prop-types.min.js'],
    inputFiles: ['**/*.js'],
    footerFiles: ['public/nf/js/navbar.js',], // this used to be navbar.es6.js but the babel transpiler dropped the .es6
    outputFile: '/navbar.js',
});

// output both
var output = mergeTrees([tree, navbar]);

if (production) {
    /* can't use this for dev mode, since it drops the sourcemap comment even if we set  output: {comments: true}
     https://github.com/mishoo/UglifyJS2/issues/653
     https://github.com/mishoo/UglifyJS2/issues/754
     https://github.com/mishoo/UglifyJS2/issues/780
     https://github.com/mishoo/UglifyJS2/issues/520
     */
    output = uglifyJavaScript(output, {
        mangle: false,
        compress: false
    });
}

module.exports = output;
