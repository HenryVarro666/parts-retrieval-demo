(function (root) {
  "use strict";
  const api = {
    runType(run) { return run.scope === 'duplicate_control' ? 'multi.control' : run.visual_enabled ? run.force_visual ? 'multi.visualRun' : 'multi.selectiveRun' : 'multi.retrievalRun'; },
    fileError(files) {
      if (!files.length || files.length > 3) return "multi.tooMany";
      for (const file of files) {
        if (file.size > 10 * 1024 * 1024) return "error.large";
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && !/\.(jpe?g|png|webp)$/i.test(file.name)) return "error.invalidFile";
      }
      return null;
    },
    predictionPayload(images, config) {
      if (!images.length || images.length > 3 || (config.pipeline === 'legacy' && images.length > 1)) throw new Error('Unsupported photo configuration');
      return {images, engine: config.engine, multiview: config.multiview, pipeline: config.pipeline, verify_visual: config.verifyVisual};
    },
    photoRecord(record, index) { return record?.photos?.[index]?.record || record; },
    score(ids, label) { return label ? {top1: ids[0] === label, top3: ids.slice(0, 3).includes(label), recall10: ids.slice(0, 10).includes(label)} : null; },
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PartsMulti = api;
})(typeof window !== 'undefined' ? window : globalThis);
