# More info at https://github.com/guard/guard#readme

ignore %r{^node_modules/}, %r{^env.*/}, %r{/tests/data/}, %r{.+\.pyc?}, %r{^Allura/docs/}, %r{.+\.log}, %r{.+\.ini}

# For autoreload of your browser, upon html/js/css changes:
#   Install http://livereload.com/extensions/
#   gem install guard-livereload
#   Then run `guard` and enable the page in your browser.
guard 'livereload' do
  watch(%r{.+\.js})
  watch(%r{.+\.css})
  watch(%r{.+\.html})
end
