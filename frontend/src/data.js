// Synthetic demonstration data. These conversations are not the organizers' DEV dataset.
export const initialCriteria = [
  {
    id: "1",
    title: "Установление контакта",
    description:
      "Оператор поздоровался на языке клиента и представился в первом ответе.",
    weight: 10,
    type: "binary",
    scale: [],
    naAllowed: false,
    naCondition: "",
  },
  {
    id: "2",
    title: "Выявление потребности",
    description:
      "Оператор учёл известные детали и уточнил недостающее до ответа.",
    weight: 15,
    type: "binary",
    scale: [],
    naAllowed: true,
    naCondition: "Данных для ответа хватало с самого начала.",
  },
  {
    id: "3",
    title: "Идентификация",
    description:
      "Проверка личности подтверждена до раскрытия данных или защищённого действия.",
    weight: 20,
    type: "binary",
    scale: [],
    naAllowed: true,
    naCondition: "Запрос не требовал идентификации.",
  },
  {
    id: "4",
    title: "Корректная и полная консультация",
    description:
      "20 — все существенные вопросы закрыты или дан корректный следующий шаг; 15 — основной вопрос решён, пропущена второстепенная деталь; 10 — существенный вопрос остался открытым; 5 — общая подсказка, но непонятно, как действовать; 0 — ответа по существу нет или ключевая рекомендация ошибочна.",
    weight: 20,
    type: "scale",
    scale: [0, 5, 10, 15, 20],
    naAllowed: true,
    naCondition: "Чат закончился до того, как клиент сформулировал запрос.",
  },
  {
    id: "5",
    title: "Эмпатия и клиентоориентированность",
    description:
      "Оператор вежлив и, если клиент выразил недовольство или описал неудобство, отреагировал на конкретную проблему.",
    weight: 15,
    type: "binary",
    scale: [],
    naAllowed: false,
    naCondition: "",
  },
  {
    id: "6",
    title: "Управление диалогом, скорость и грамотность",
    description:
      "10 — ответы ясные и связные, при явном ожидании оператор предупредил; 7 — один заметный сбой; 4 — клиент переспрашивает из-за формулировок или порядка; 0 — бессвязные или противоречивые реплики мешают понять диалог. Порог первой реакции 3 минуты, теги и вложения не оцениваются.",
    weight: 15,
    type: "scale",
    scale: [0, 4, 7, 10],
    naAllowed: false,
    naCondition: "",
  },
  {
    id: "7",
    title: "Завершение",
    description:
      "Оператор подвёл итог или предложил дальнейшую помощь и попрощался.",
    weight: 5,
    type: "binary",
    scale: [],
    naAllowed: true,
    naCondition: "Чат оборвался до возможности его завершить.",
  },
  {
    id: "8",
    title: "Грубые ошибки",
    description:
      "Да — выявлено оскорбление клиента, предложение платной услуги в обход компании или раскрытие конфиденциальной информации. Нет — ни одно из трёх не выявлено. Отмечается отдельно и не обнуляет итог автоматически.",
    weight: 0,
    type: "flag",
    scale: [],
    naAllowed: false,
    naCondition: "",
  },
];

export function scoreEvaluation(criteria, results) {
  let earned = 0;
  let available = 0;
  let critical = false;
  for (const criterion of criteria) {
    const result = results.find(
      (item) => String(item.criterionId) === String(criterion.id),
    );
    if (!result) return { score: null, critical, incomplete: true };
    const value = result.answer;
    if (criterion.type === "flag") {
      if (!["Да", "Нет"].includes(value))
        return { score: null, critical, incomplete: true };
      critical ||= value === "Да";
      continue;
    }
    if (value === "N/A" && criterion.naAllowed) continue;
    const weight = Number(criterion.weight);
    if (!Number.isFinite(weight) || weight < 0)
      return { score: null, critical, incomplete: true };
    let normalized;
    if (criterion.type === "scale") {
      const levels = criterion.scale.map(Number);
      const max = Math.max(...levels);
      if (typeof value !== "number" || !levels.includes(value) || max <= 0)
        return { score: null, critical, incomplete: true };
      normalized = value / max;
    } else {
      if (!["Да", "Нет"].includes(value))
        return { score: null, critical, incomplete: true };
      normalized = value === "Да" ? 1 : 0;
    }
    earned += weight * normalized;
    available += weight;
  }
  return {
    score: available ? Math.round((earned / available) * 10000) / 100 : null,
    critical,
  };
}

const m = (id, role, text, time) => ({ id, role, text, time });
const r = (criterionId, answer, reason, evidenceId) => ({
  criterionId,
  answer,
  reason,
  evidenceId,
});
const results = (overrides = {}) =>
  [
    r(
      "1",
      "Да",
      "Оператор поприветствовал клиента и представился в первом ответе.",
      "m2",
    ),
    r(
      "2",
      "Да",
      "До консультации оператор уточнил существенные детали запроса.",
      "m4",
    ),
    r(
      "3",
      "N/A",
      "Общая консультация не требует раскрытия персональных данных или защищённого действия.",
      "m1",
    ),
    r(
      "4",
      20,
      "Предложены конкретные действия, которые закрывают существенные вопросы клиента.",
      "m6",
    ),
    r(
      "5",
      "Да",
      "Оператор вежлив и отреагировал на описанное клиентом неудобство.",
      "m2",
    ),
    r(
      "6",
      10,
      "Ответы понятны, связаны с запросом и даны в последовательном порядке.",
      "m6",
    ),
    r("7", "Да", "Предложена дальнейшая помощь и есть прощание.", "m8"),
    r(
      "8",
      "Нет",
      "В проверенном диалоге не выявлены оскорбления, обход компании или раскрытие конфиденциальных данных.",
      "m8",
    ),
  ].map((item) =>
    overrides[item.criterionId]
      ? { ...item, ...overrides[item.criterionId] }
      : item,
  );

const raw = [
  {
    id: "CQA-1048",
    customer: "Александр Ким",
    initials: "АК",
    agent: "Алина Садыкова",
    channel: "chat",
    language: "RU",
    topic: "Вывод средств",
    date: "Сегодня, 12:42",
    status: "review",
    duration: "8 мин 24 сек",
    messages: [
      m(
        "m1",
        "client",
        "Здравствуйте. Третий день не могу вывести деньги на карту. Заявка висит в обработке. Сколько ещё ждать?",
        "12:42",
      ),
      m(
        "m2",
        "operator",
        "Здравствуйте, Александр! Меня зовут Алина. Понимаю, как неприятно ждать перевода. Давайте разберёмся.",
        "12:42",
      ),
      m(
        "m3",
        "client",
        "Номер заявки 48291. Деньги нужны сегодня, очень прошу помочь.",
        "12:43",
      ),
      m(
        "m4",
        "operator",
        "Подскажите, заявка была создана в пятницу? И вы выводите средства на банковскую карту или по реквизитам счёта?",
        "12:43",
      ),
      m(
        "m5",
        "client",
        "Да, в пятницу вечером. На карту. И ещё: могу я отменить заявку и сделать новую?",
        "12:44",
      ),
      m(
        "m6",
        "operator",
        "Заявки обрабатываются в рабочие дни. Статус можно посмотреть в приложении: «Портфель» → «Переводы» → «История». Если статус не изменится, напишите нам повторно.",
        "12:46",
      ),
      m(
        "m7",
        "client",
        "А что насчёт отмены? И сколько именно рабочих дней ждать?",
        "12:47",
      ),
      m(
        "m8",
        "operator",
        "Обычно обработка занимает некоторое время. Спасибо за обращение, хорошего дня!",
        "12:50",
      ),
    ],
    results: results({
      4: {
        answer: 10,
        reason:
          "Оператор объяснил общий порядок обработки, но не ответил на два существенных вопроса: о сроке ожидания и возможности отменить заявку.",
        evidenceId: "m7",
      },
      6: {
        answer: 7,
        reason:
          "Структура ответа в целом понятна, но неопределённая формулировка о сроке привела к повторному вопросу клиента.",
        evidenceId: "m7",
      },
    }),
  },
  {
    id: "CQA-1047",
    customer: "Аружан Омарова",
    initials: "АО",
    agent: "Данияр Ахметов",
    channel: "chat",
    language: "KZ",
    topic: "Открытие счёта",
    date: "Сегодня, 12:31",
    status: "done",
    duration: "4 мин 12 сек",
    messages: [
      m(
        "m1",
        "client",
        "Сәлеметсіз бе! Брокерлік шотты қосымша арқылы ашуға бола ма?",
        "12:31",
      ),
      m(
        "m2",
        "operator",
        "Сәлеметсіз бе! Менің атым Данияр. Иә, шотты қосымша арқылы ашуға болады.",
        "12:31",
      ),
      m(
        "m3",
        "client",
        "Қандай құжаттар қажет және қай бөлімге кіруім керек?",
        "12:32",
      ),
      m(
        "m4",
        "operator",
        "Сізде қосымша орнатылған ба және жеке куәлігіңіз қолыңызда ма?",
        "12:32",
      ),
      m("m5", "client", "Иә, қосымша бар, жеке куәлігім де дайын.", "12:33"),
      m(
        "m6",
        "operator",
        "Басты беттен «Шот ашу» бөлімін таңдаңыз. Жеке куәлікті дайындап, қосымшадағы сәйкестендіру қадамдарын орындаңыз. Өтініш мәртебесі сол бөлімде көрсетіледі.",
        "12:34",
      ),
      m("m7", "client", "Түсінікті, рахмет!", "12:35"),
      m(
        "m8",
        "operator",
        "Қосымша сұрақ туындаса, бізге жазыңыз. Күніңіз сәтті өтсін!",
        "12:35",
      ),
    ],
    results: results(),
  },
  {
    id: "CQA-1046",
    customer: "Emma Wilson",
    initials: "EW",
    agent: "Мария Волкова",
    channel: "call",
    language: "EN",
    topic: "Доступ в приложение",
    date: "Сегодня, 12:18",
    status: "done",
    duration: "5 мин 38 сек",
    messages: [
      m(
        "m1",
        "client",
        "Hi, I cannot sign in. The app says my password is incorrect.",
        "2026-11-07T12:18:00+05:00",
      ),
      m(
        "m2",
        "operator",
        "Hello! My name is Maria. I understand being locked out is frustrating. I can explain the recovery process.",
        "2026-11-07T12:18:12+05:00",
      ),
      m(
        "m3",
        "client",
        "I still have access to the phone number linked to my account.",
        "2026-11-07T12:19:00+05:00",
      ),
      m(
        "m4",
        "operator",
        "Have you already tried the “Forgot password” option on the sign-in screen?",
        "2026-11-07T12:19:20+05:00",
      ),
      m(
        "m5",
        "client",
        "No, I have not. Where do I find it?",
        "2026-11-07T12:20:00+05:00",
      ),
      m(
        "m6",
        "operator",
        "Tap “Forgot password” below the password field. Follow the verification steps in the app and create a new password. Do not share your verification code with anyone, including support.",
        "2026-11-07T12:21:00+05:00",
      ),
      m("m7", "client", "That worked. Thank you!", "2026-11-07T12:23:00+05:00"),
      m(
        "m8",
        "operator",
        "Glad you are back in. If you need anything else, please contact us. Goodbye!",
        "2026-11-07T12:23:38+05:00",
      ),
    ],
    results: results(),
  },
  {
    id: "CQA-1045",
    customer: "Дмитрий Петров",
    initials: "ДП",
    agent: "Алина Садыкова",
    channel: "chat",
    language: "RU",
    topic: "Комиссии и тарифы",
    date: "Сегодня, 11:56",
    status: "done",
    duration: "3 мин 18 сек",
    messages: [
      m(
        "m1",
        "client",
        "Где посмотреть актуальные тарифы на сделки с акциями?",
        "11:56",
      ),
      m(
        "m2",
        "operator",
        "Здравствуйте! Меня зовут Алина. Актуальные условия доступны на официальном сайте в разделе «Тарифы».",
        "11:56",
      ),
      m("m3", "client", "А в приложении этот раздел тоже есть?", "11:57"),
      m(
        "m4",
        "operator",
        "Да. Откройте «Профиль», затем «Документы и тарифы».",
        "11:57",
      ),
      m("m5", "client", "Нашёл, спасибо.", "11:58"),
      m(
        "m6",
        "operator",
        "Перед сделкой также проверьте комиссию на экране подтверждения.",
        "11:58",
      ),
      m("m7", "client", "Хорошо.", "11:59"),
      m(
        "m8",
        "operator",
        "Если появятся другие вопросы, будем рады помочь. Хорошего дня!",
        "11:59",
      ),
    ],
    results: results({
      2: {
        answer: "N/A",
        reason:
          "В первом сообщении достаточно данных для общей консультации о расположении тарифов.",
        evidenceId: "m1",
      },
    }),
  },
  {
    id: "CQA-1044",
    customer: "Екатерина Ли",
    initials: "ЕЛ",
    agent: "Игорь Смирнов",
    channel: "chat",
    language: "RU",
    topic: "Смена номера телефона",
    date: "Сегодня, 11:40",
    status: "review",
    duration: "6 мин 10 сек",
    messages: [
      m(
        "m1",
        "client",
        "Хочу изменить номер телефона в моём профиле. Старый номер недоступен.",
        "11:40",
      ),
      m(
        "m2",
        "operator",
        "Здравствуйте, меня зовут Игорь. Помогу с обращением.",
        "11:40",
      ),
      m("m3", "client", "Могу прислать новый номер здесь?", "11:41"),
      m(
        "m4",
        "operator",
        "Скажите, у вас остался доступ в приложение?",
        "11:41",
      ),
      m("m5", "client", "Да, приложение открывается.", "11:42"),
      m(
        "m6",
        "operator",
        "Откройте защищённый раздел «Профиль» → «Безопасность» и запустите процедуру смены номера. Выполните проверку личности в приложении.",
        "11:43",
      ),
      m(
        "m7",
        "client",
        "У меня нет пункта «Смена номера». Что делать?",
        "11:44",
      ),
      m(
        "m8",
        "operator",
        "Посмотрите внимательнее в настройках. Всего доброго.",
        "11:46",
      ),
    ],
    results: results({
      4: {
        answer: 5,
        reason:
          "Предложена общая подсказка, но после сообщения об отсутствии нужного пункта клиенту не дан рабочий следующий шаг.",
        evidenceId: "m8",
      },
      6: {
        answer: 7,
        reason:
          "Последний ответ не продолжает решение описанного затруднения, хотя предыдущие шаги изложены понятно.",
        evidenceId: "m8",
      },
      7: {
        answer: "Нет",
        reason:
          "Оператор попрощался, но не подвёл итог и не предложил дальнейшую помощь.",
        evidenceId: "m8",
      },
    }),
  },
  {
    id: "CQA-1043",
    customer: "Нұрлан Әбілов",
    initials: "НӘ",
    agent: "Данияр Ахметов",
    channel: "chat",
    language: "KZ",
    topic: "Пополнение счёта",
    date: "Сегодня, 11:25",
    status: "done",
    duration: "4 мин 05 сек",
    messages: [
      m(
        "m1",
        "client",
        "Сәлеметсіз бе, шотты қалай толтыруға болады?",
        "11:25",
      ),
      m(
        "m2",
        "operator",
        "Сәлеметсіз бе! Менің атым Данияр. Көмектесуге дайынмын.",
        "11:25",
      ),
      m("m3", "client", "Банк қосымшасы арқылы аударғым келеді.", "11:26"),
      m("m4", "operator", "Аударымды теңгемен жасағыңыз келе ме?", "11:26"),
      m("m5", "client", "Иә, теңгемен.", "11:27"),
      m(
        "m6",
        "operator",
        "Біздің қосымшада «Толықтыру» бөлімін ашып, теңге шотының деректемелерін көшіріңіз. Банк қосымшасында осы деректемелер бойынша аударым жасаңыз. Аударымды растау алдында алушы мен комиссияны тексеріңіз.",
        "11:28",
      ),
      m("m7", "client", "Рахмет, түсіндім.", "11:29"),
      m(
        "m8",
        "operator",
        "Тағы сұрақ болса, хабарласыңыз. Сау болыңыз!",
        "11:29",
      ),
    ],
    results: results(),
  },
  {
    id: "CQA-1042",
    customer: "James Miller",
    initials: "JM",
    agent: "Мария Волкова",
    channel: "chat",
    language: "EN",
    topic: "Налоговые документы",
    date: "Сегодня, 11:08",
    status: "done",
    duration: "3 мин 46 сек",
    messages: [
      m(
        "m1",
        "client",
        "Hello, where can I download my account statement for last year?",
        "11:08",
      ),
      m(
        "m2",
        "operator",
        "Hello! My name is Maria. I can guide you to the document section.",
        "11:08",
      ),
      m("m3", "client", "I need a full-year statement as a PDF.", "11:09"),
      m(
        "m4",
        "operator",
        "Are you using the mobile app or the web account?",
        "11:09",
      ),
      m("m5", "client", "The mobile app.", "11:10"),
      m(
        "m6",
        "operator",
        "Open “Profile” → “Reports”, select the start and end dates for last year, and choose PDF. Generate the report and use the download button when it is ready.",
        "11:10",
      ),
      m("m7", "client", "Found it, thank you.", "11:11"),
      m(
        "m8",
        "operator",
        "You are welcome. Please let us know if you need help with the download. Goodbye!",
        "11:11",
      ),
    ],
    results: results(),
  },
  {
    id: "CQA-1041",
    customer: "Михаил Орлов",
    initials: "МО",
    agent: "Игорь Смирнов",
    channel: "call",
    language: "RU",
    topic: "Статус заявки",
    date: "Сегодня, 10:52",
    status: "review",
    duration: "7 мин 02 сек",
    messages: [
      m(
        "m1",
        "client",
        "Добрый день, хочу узнать статус моей заявки на перевод.",
        "2026-11-07T10:52:00+05:00",
      ),
      m(
        "m2",
        "operator",
        "Здравствуйте! Меня зовут Игорь. Давайте уточним информацию.",
        "2026-11-07T10:52:12+05:00",
      ),
      m(
        "m3",
        "client",
        "Номер заявки 9731, создал вчера.",
        "2026-11-07T10:53:00+05:00",
      ),
      m(
        "m4",
        "operator",
        "Подскажите, это перевод между вашими счетами или вывод в банк?",
        "2026-11-07T10:53:12+05:00",
      ),
      m("m5", "client", "Вывод в банк.", "2026-11-07T10:54:00+05:00"),
      m(
        "m6",
        "operator",
        "По вашей заявке отправлен перевод на счёт, заканчивающийся на 4582. Сумма перевода — 150 тысяч тенге.",
        "2026-11-07T10:55:00+05:00",
      ),
      m("m7", "client", "Спасибо, это всё.", "2026-11-07T10:58:00+05:00"),
      m(
        "m8",
        "operator",
        "Перевод отправлен. Если понадобится помощь, обращайтесь. До свидания!",
        "2026-11-07T10:59:02+05:00",
      ),
    ],
    results: results({
      3: {
        answer: "Нет",
        reason:
          "До раскрытия суммы и реквизитов конкретного перевода в транскрипте нет подтверждения проверки личности.",
        evidenceId: "m6",
      },
      8: {
        answer: "Да",
        reason:
          "Раскрыты сумма и часть реквизитов персональной операции без подтверждённой идентификации в представленном транскрипте.",
        evidenceId: "m6",
      },
    }),
  },
  {
    id: "CQA-1040",
    customer: "Айгерім Сәрсен",
    initials: "АС",
    agent: "Данияр Ахметов",
    channel: "chat",
    language: "KZ",
    topic: "Уведомления",
    date: "Сегодня, 10:37",
    status: "pending",
    duration: "2 мин 18 сек",
    messages: [
      m(
        "m1",
        "client",
        "Қосымшадағы хабарламалар келмей жатыр. Қайдан қосуға болады?",
        "10:37",
      ),
      m(
        "m2",
        "operator",
        "Сәлеметсіз бе! Менің атым Данияр. Бірге тексеріп көрейік.",
        "10:37",
      ),
      m("m3", "client", "Телефоным Android.", "10:38"),
      m(
        "m4",
        "operator",
        "Телефон баптауларында қосымшаға хабарлама жіберуге рұқсат берілген бе?",
        "10:38",
      ),
      m("m5", "client", "Жоқ екен.", "10:38"),
      m(
        "m6",
        "operator",
        "Телефон баптауларынан қосымшаны ашып, хабарламаларға рұқсат беріңіз. Одан кейін қосымшадағы «Баптаулар» → «Хабарламалар» бөлімін тексеріңіз.",
        "10:39",
      ),
      m("m7", "client", "Қостым, рахмет!", "10:39"),
      m(
        "m8",
        "operator",
        "Көмектесе алғаныма қуаныштымын. Сұрақ болса, хабарласыңыз. Сау болыңыз!",
        "10:39",
      ),
    ],
    results: results(),
  },
  {
    id: "CQA-1039",
    customer: "София Иванова",
    initials: "СИ",
    agent: "Алина Садыкова",
    channel: "chat",
    language: "RU",
    topic: "Покупка ценных бумаг",
    date: "Сегодня, 10:20",
    status: "done",
    duration: "4 мин 32 сек",
    messages: [
      m(
        "m1",
        "client",
        "Добрый день! Как найти облигацию по тикеру в приложении?",
        "10:20",
      ),
      m(
        "m2",
        "operator",
        "Здравствуйте! Меня зовут Алина. Подскажу, как воспользоваться поиском.",
        "10:20",
      ),
      m(
        "m3",
        "client",
        "Я знаю тикер, но не понимаю, где его вводить.",
        "10:21",
      ),
      m("m4", "operator", "У вас открыт раздел «Рынок»?", "10:21"),
      m("m5", "client", "Да, открыла.", "10:22"),
      m(
        "m6",
        "operator",
        "Нажмите значок поиска сверху и введите тикер. Откройте карточку найденного инструмента. Перед размещением заявки проверьте название, валюту и параметры облигации.",
        "10:23",
      ),
      m("m7", "client", "Нашла нужную, спасибо за помощь.", "10:24"),
      m(
        "m8",
        "operator",
        "Рада помочь! Если появятся вопросы по работе приложения, напишите нам. До свидания!",
        "10:24",
      ),
    ],
    results: results(),
  },
];

export const conversations = raw.map((conversation) => ({
  ...conversation,
  results: conversation.status === "pending" ? [] : conversation.results,
  score:
    conversation.status === "pending"
      ? null
      : scoreEvaluation(initialCriteria, conversation.results).score,
  critical:
    conversation.status === "pending"
      ? false
      : scoreEvaluation(initialCriteria, conversation.results).critical,
}));
