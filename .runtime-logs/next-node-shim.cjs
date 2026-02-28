const Module = require('module');
const origLoad = Module._load;
Module._load = function patchedLoad(request, parent, isMain) {
  const loaded = origLoad.call(this, request, parent, isMain);
  if (request === 'next/dist/compiled/semver') {
    if (loaded && typeof loaded.lt === 'function') loaded.lt = () => false;
    if (loaded && loaded.default && typeof loaded.default.lt === 'function') loaded.default.lt = () => false;
  }
  return loaded;
};
