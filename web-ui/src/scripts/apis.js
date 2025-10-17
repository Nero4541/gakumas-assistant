import axiosplus from "@/scripts/utils/axios.js";

/**
 * 开始执行任务队列
 * @return {Promise<AxiosResponse<any, any>>}
 */
function start_task_queue() {
  return axiosplus.get("/api/task/start");
}

/**
 * 终止执行任务队列
 * @return {Promise<AxiosResponse<any, any>>}
 */
function stop_task_queue() {
  return axiosplus.get("/api/task/stop");
}

/**
 * 执行指定任务
 * @param task_name 任务名
 * @return {Promise<axios.AxiosResponse<any>>}
 */
function run_task(task_name) {
  return axiosplus.get(`/api/task/start/${task_name}`);
}

/**
 * 获取后端状态
 * @return {Promise<AxiosResponse<any, any>>}
 */
function get_status() {
  return axiosplus.get("/api/status");
}

/**
 * 获取所有已注册的任务
 * @return {Promise<AxiosResponse<any, any>>}
 */
function get_registered_tasks() {
  return axiosplus.get("/api/task/get_registered_tasks")
}

/**
 * 禁用任务
 * @param task_name 任务名
 * @return {Promise<axios.AxiosResponse<any>>}
 */
function disable_task(task_name) {
  return axiosplus.post(`/api/task/disable/${task_name}`);
}

/**
 * 启用任务
 * @param task_name 任务名
 * @returns {Promise<axios.AxiosResponse<any>>}
 */
function enable_task(task_name) {
  return axiosplus.post(`/api/task/enable/${task_name}`);
}

/**
 * 切换模型
 * @param model_name 模型名
 * @returns {Promise<axios.AxiosResponse<any>>}
 */
function switch_yolo_model(model_name) {
  return axiosplus.get(`/api/debug/switch_yolo_model/${model_name}`);
}
/**
 * 获取配置
 * @return {Promise<axios.AxiosResponse<any>>}
 */
function get_config(){
  return axiosplus.get("/api/config");
}

/**
 * 获取指定任务配置
 * @param task_name 任务名
 * @returns {Promise<axios.AxiosResponse<any>>}
 */
function get_task_config(task_name) {
  return axiosplus.get(`/api/config/${task_name}`);
}

/**
 * 保存配置
 * @param data 配置数据
 * @return {Promise<axios.AxiosResponse<any>>}
 */
function save_config(data){
  return axiosplus.put(`/api/config`, data);
}

/**
 * 保存指定任务的配置
 * @param task_name 任务名
 * @param data 任务配置数据
 * @returns {Promise<axios.AxiosResponse<any>>}
 */
function save_task_config(task_name, data) {
  return axiosplus.put(`/api/config/${task_name}`, data);
}

/**
 * 获取所有ADB设备列表
 * @param only_usb_device 仅获取USB设备
 */
function get_all_adb_device(only_usb_device=false) {
  if (!only_usb_device) {
    return axiosplus.get("/api/adb/devices");
  }
  return axiosplus.get(`/api/adb/devices/usb`);
}

/**
 * 获取所有物品列表
 */
function get_all_item() {
  return axiosplus.get("/api/item/list");
}

export default {
  start_task_queue,
  stop_task_queue,
  run_task,
  get_status,
  get_registered_tasks,
  disable_task,
  enable_task,
  switch_yolo_model,
  get_config,
  save_config,
  get_task_config,
  save_task_config,
  get_all_adb_device,
  get_all_item,
}
