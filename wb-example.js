var axProStates = {
  1: {en: 'Armed', ru: 'Под охраной'},
  2: {en: 'Stay armed', ru: 'Ночной режим'},
  3: {en: 'Disarmed', ru: 'Снято с охраны'},
  4: {en: 'Status unknown', ru: 'Состояние неизвестно'}
};

var ciaToState = {
  '3401': 1,
  '3441': 2,
  '1401': 3
};

defineVirtualDevice('AxPro', {
    title: {en: 'Ax Pro', ru: 'Ax Pro'} ,
    cells: {
      state_01: {
        title: {en: 'Ground floor', ru: 'Подвал'},
        type: "value",
        value: 4,
        enum: axProStates
      },
      state_02: {
        title: {en: 'Bar', ru: 'Бар'},
        type: "value",
        value: 4,
        enum: axProStates
      },
      state_03: {
        title: {en: 'Outdoor', ru: 'Улица'},
        type: "value",
        value: 4,
        enum: axProStates
      }
    }
});

// Sync with virtual device
trackMqtt("/ax-pro/partitions/#", function(message) {
  log.debug("name: {}, value: {}".format(message.topic, message.value));
  
  var value = JSON.parse(message.value);
  var state = ciaToState[value.cia_code];
  
  if (state !== undefined){
    if (value.group_or_partition_number == '01') {
      dev["AxPro/state_01"] = state;
    } else if (value.group_or_partition_number == '02') {
      dev["AxPro/state_02"] = state;
    } else if (value.group_or_partition_number == '03') {
      dev["AxPro/state_03"] = state;
    }
  }

});

defineRule("ArmGroundFloor",{
  whenChanged: "AxPro/state_01",
  then: function (newValue, devName, cellName) {
    if (newValue == 1) {
      log.info("Подвал поставлен на охрану");
    }
  }
});