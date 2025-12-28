const IMAGES = import.meta.glob<string>(
  '@/assets/BandaiNamco/face/*.png',
  {
    eager: true,
    import: 'default',
  }
)

type AccentColorMap = Record<string, string>

const ACCENT_COLORS: AccentColorMap = {
  "hski": "#FF4F64",  // 花海 咲季
  "ttmr": "#27B4EB",  // 月村 手毬
  "fktn": "#FFD203",  // 藤田 ことね
  "hrnm": "#FD7EC2",  // 姫崎 莉波
  "ssmk": "#92DE5A",  // 紫雲 清夏
  "shro": "#00BED8",  // 篠澤 広
  "kllj": "#D2E3E4",  // 葛城 リーリヤ
  "kcna": "#FE8A22",  // 倉本 千奈
  "amao": "#C45DC8",  // 有村 麻央
  "hume": "#F74C2C",  // 花海 佑芽
  "hmsz": "#6EA3FC",  // 秦谷 美鈴
  "jsna": "#FFAC28",  // 十王 星南
  "nasr": "#8D6C71",  //
  "atbm": "#8874FF",  // 雨夜 燕
};

function getColorFromImage(path: string): string {
  const key = path.match(/img_sd_(.*?)_face/)?.[1]
  return key && ACCENT_COLORS[key]
    ? ACCENT_COLORS[key]
    : 'rgb(243,142,61)'
}

export interface Theme {
  icon: string
  color: string
}

export function getRandomTheme(): Theme {
  const images = Object.values(IMAGES)

  if (images.length === 0) {
    return {
      icon: '',
      color: 'rgb(243,142,61)',
    }
  }

  const icon = images[Math.floor(Math.random() * images.length)]

  return {
    icon,
    color: getColorFromImage(icon),
  }
}
