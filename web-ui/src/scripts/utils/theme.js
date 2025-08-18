let IMAGES = import.meta.glob('@/assets/BandaiNamco/face/*.png', { eager: true, import: 'default' })

IMAGES = Object.values(IMAGES)

const ACCENT_COLORS = {
  "hski": "#FF4F64",
  "ttmr": "#27B4EB",
  "fktn": "#FFD203",
  "hrnm": "#FD7EC2",
  "ssmk": "#92DE5A",
  "shro": "#00BED8",
  "kllj": "#D2E3E4",
  "kcna": "#FE8A22",
  "amao": "#C45DC8",
  "hume": "#F74C2C",
  "hmsz": "#6EA3FC",
  "jsna": "#FFAC28",
  "nasr": "#8D6C71",
};

function _getColorFromImage(path) {
  const key = path.match(/img_sd_(.*?)_face/)?.[1]
  return ACCENT_COLORS[key] || "rgb(243,142,61)"
}

export function getRandomTheme() {
  const target_img = IMAGES[Math.floor(Math.random() * IMAGES.length)]
  return {
    icon: target_img,
    color: _getColorFromImage(target_img),
  }
}
