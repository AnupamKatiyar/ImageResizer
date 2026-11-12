export default {
  multipass: true,
  plugins: [
    {
      name: "preset-default",
      params: {
        overrides: {
          removeViewBox: false,
          removeHiddenElems: false,
          removeUselessDefs: false,
          cleanupIds: false,
          cleanupNumericValues: {
            floatPrecision: 3,
          },
          convertPathData: {
            floatPrecision: 3,
          },
          convertTransform: {
            floatPrecision: 3,
          },
        },
      },
    },
  ],
};
